"""Orchestrator: holds subsystems, estimators, and the self-model.

The :class:`Engine` is the headless heart of the simulator. ``tick()``
advances every subsystem by ``dt``, feeds each estimator its observation,
and asks the self-model to refresh its capability claims. The engine is
usable without an MCP server, which keeps the tick loop testable in pure
Python.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .audit import AuditLogger, AuditRecord, redact
from .clocks import Clock, MonotonicClock
from .config import Settings, get_settings
from .db import DtnStore, StateTransitionLog
from .estimators.apu import ApuEstimator
from .estimators.biometrics import BiometricsKalman
from .estimators.comms import CommsParticleFilter
from .estimators.compute import ComputeKalman
from .estimators.eoir import EoirKalman
from .estimators.position_ekf import PositionEkf
from .estimators.power import PowerEstimator
from .estimators.sensors import EnvironmentalKalman
from .estimators.storage import StorageKalman
from .estimators.thermal import ThermalKalman
from .policy import Tier
from .safety import SafetyResult
from .state.comms_outbox import CommsOutbox
from .state.comms_state import CommsState
from .state.dtn_mesh import DtnMesh
from .state.failsafe import FailsafeArbiter, FailsafeCondition
from .state.machine import (
    REQ_COMMS_LINK,
    REQ_OPERATOR,
    SC_POWER_RESERVE,
    SC_THERMAL_HEADROOM,
    GuardDenied,
    Mode,
    StateMachine,
    build_fsm_enforcer,
    is_impaired,
    is_operational,
)
from .state.operator_state import OperatorState
from .state.operator_state import derive as derive_operator
from .subsystems.apu import ApuSubsystem
from .subsystems.biometrics import BiometricsSubsystem
from .subsystems.comms import CommsSubsystem
from .subsystems.compute import ComputeSubsystem
from .subsystems.eoir import EoirSubsystem
from .subsystems.imu import ImuSubsystem
from .subsystems.inference import InferenceSubsystem
from .subsystems.pmu import PmuSubsystem
from .subsystems.position import PositionSubsystem
from .subsystems.sensors import SensorsSubsystem
from .subsystems.storage import StorageSubsystem
from .subsystems.terrain import TerrainModel, WorldSource
from .subsystems.thermal import ThermalSubsystem
from .types import TickContext

__all__ = ["Engine", "EngineState", "TickHook"]

TickHook = Callable[[TickContext], None]


# Safety-critical numeric profile fields (section, key). They feed the SC-8
# power-reserve and SC-2 thermal-headroom gates as floats; a non-numeric value
# here would crash the tick loop in ``_safety_context`` rather than failing
# closed, and is reachable through the ``profile_reload`` tool (ADR 0029).
_SAFETY_NUMERIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("power", "soc_pct_critical_threshold"),
    ("thermal", "headroom_threshold_c"),
)


class ProfileModel(BaseModel):
    """Minimal schema gate for hardware profile YAML files."""

    model_config = ConfigDict(extra="allow")
    name: str

    @model_validator(mode="before")
    @classmethod
    def _safety_sections_wellformed(cls, data: Any) -> Any:
        """Refuse a malformed safety section or threshold at load (ADR 0029).

        The SC-8 / SC-2 gates read the ``power`` and ``thermal`` sections; a
        non-mapping section (e.g. ``power: []``) crashes subsystem construction
        and ``_safety_context``, and a non-numeric threshold crashes the tick
        loop. Both are reachable through ``profile_reload``. Validating them
        here means a bad reload is rejected before any subsystem is rebuilt, so
        the previous good profile stays live and the tick loop never meets a
        malformed reserve.
        """
        if isinstance(data, Mapping):
            for section, key in _SAFETY_NUMERIC_FIELDS:
                block = data.get(section)
                if block is None:
                    continue
                if not isinstance(block, Mapping):
                    raise ValueError(
                        f"profile section {section!r} must be a mapping"
                    )
                if key in block:
                    _require_finite_number(block[key], f"{section}.{key}")
        return data


@dataclass
class EngineState:
    tick: int = 0
    ts_s: float = 0.0
    mode: Mode = Mode.STOWED
    operator_state: OperatorState = OperatorState.NOMINAL
    operator_state_reason: str = ""
    comms_state: CommsState = CommsState.CONNECTED
    comms_state_reason: str = ""
    last_capabilities: dict[str, float] = field(default_factory=dict)


# Modes whose function depends on a live comms link. Only these auto-safe on
# a denied link (ADR 0028, narrowed to the approved "link modes" scope): a
# MISSION or MONITORING run that does not need comms is not degraded by a
# dead link.
_LINK_MODES = frozenset({Mode.RELAY, Mode.C2})

# Compute-load ceilings applied as FSM entry actions (ADR 0029). Entering a
# safed or throttled posture caps delivered load so auto-safing actuates
# rather than only relabelling: SAFE drops to a minimal heartbeat, LOW_POWER
# sheds enough to slow the drain it is named for, THERMAL_LIMIT caps to a
# cool-down load. DEGRADED keeps full load (it is the generic / comms posture,
# not a power or thermal command); modes absent from the table clear the cap.
_MODE_LOAD_CEILINGS: dict[Mode, float] = {
    Mode.SAFE: 5.0,
    Mode.LOW_POWER: 15.0,
    Mode.THERMAL_LIMIT: 40.0,
}

# Consecutive ticks the operator-incapacitation label must hold before the
# auto-safe fires (ADR 0029). The label reads the biometrics Kalman estimate,
# so a single-tick spike must not force a one-way SAFE.
_OPERATOR_PERSISTENCE_TICKS = 3

# The auto-safe policy as a declarative table (ADR 0044). Severity orders the
# firing when several conditions trip at once: operator incapacitation takes
# the full SAFE and outranks the device hazards; power (the least recoverable
# drain, whose LOW_POWER shedding also relieves heat) precedes thermal; the
# comms-denied condition trails them. The operator condition is debounced over
# ``_OPERATOR_PERSISTENCE_TICKS`` with anti-toggle decay, so a single-tick
# recovery does not reset the streak; the device hazards and the comms
# condition stay instantaneous. The ids are shared with the entry gate
# (ADR 0046), so a refusal and an auto-safe firing land under one constraint id
# in the audit trail. ``Engine._failsafe_detect`` supplies the raw-active set
# the ``FailsafeArbiter`` debounces and selects from.
_FAILSAFE_CONDITIONS: tuple[FailsafeCondition, ...] = (
    FailsafeCondition(
        id=REQ_OPERATOR,
        severity=40,
        debounce_ticks=_OPERATOR_PERSISTENCE_TICKS,
        decay=1,
        preferred="safe",
        fallback="safe",
    ),
    FailsafeCondition(
        id=SC_POWER_RESERVE,
        severity=30,
        debounce_ticks=1,
        decay=1,
        preferred="low_power",
        fallback="degrade",
    ),
    FailsafeCondition(
        id=SC_THERMAL_HEADROOM,
        severity=20,
        debounce_ticks=1,
        decay=1,
        preferred="thermal_limit",
        fallback="degrade",
    ),
    FailsafeCondition(
        id=REQ_COMMS_LINK,
        severity=10,
        debounce_ticks=1,
        decay=1,
        preferred="degrade",
        fallback="degrade",
    ),
)


class Engine:
    """Tick-driven simulator orchestrator."""

    def __init__(
        self,
        settings: Settings | None = None,
        profile: Mapping[str, Any] | None = None,
        scenario: Mapping[str, Any] | None = None,
        transition_log: StateTransitionLog | None = None,
        *,
        seed: int | None = None,
        clock: Clock | None = None,
        audit: AuditLogger | None = None,
        terrain: WorldSource | None = None,
    ) -> None:
        self.settings: Settings = settings or get_settings()
        self.profile: Mapping[str, Any] = profile or _load_profile(self.settings.profile)
        self.scenario: Mapping[str, Any] | None = scenario
        self.audit = audit
        self.safety = build_fsm_enforcer()
        self.fsm = StateMachine(checker=self.safety)
        self.state = EngineState(mode=self.fsm.current)
        self.transition_log = transition_log or StateTransitionLog(None)
        self.dtn_store = DtnStore(
            self.transition_log.engine, init_error=self.transition_log.init_error
        )
        self._started = False
        self._failsafe = FailsafeArbiter(_FAILSAFE_CONDITIONS)
        self._tick_hooks: list[TickHook] = []
        self.tick_hook_errors = 0
        # ADR 0019 deterministic seed + clock seams. ``seed=None``
        # falls back to OS entropy (current behaviour); ``clock=None``
        # picks the real ``MonotonicClock``. A test that needs a
        # reproducible trajectory passes ``seed=42`` and asserts
        # against the deterministic output; a test that needs to
        # drive the time line passes a ``VirtualClock(start_s=0.0)``.
        self.seed = seed
        self.rng: np.random.Generator = np.random.default_rng(seed)
        self.clock: Clock = clock or MonotonicClock()

        # ADR 0019 follow-up: thread the engine RNG into every
        # subsystem at construction so future noise sampling can draw
        # from a deterministic seam.
        self.pmu = PmuSubsystem.from_profile(self.profile, rng=self.rng)
        self.power = self.pmu.active_battery
        self.apu = ApuSubsystem(self.profile, rng=self.rng)
        self.thermal = ThermalSubsystem(self.profile, rng=self.rng)
        self.compute = ComputeSubsystem(self.profile, rng=self.rng)
        self.inference = InferenceSubsystem(
            self.profile, compute=self.compute, rng=self.rng
        )
        self.storage = StorageSubsystem(self.profile, rng=self.rng)
        # BL-089: the shared procedural world (None unless the profile carries a
        # `world` section); the comms link budget samples it for terrain diffraction.
        # ADR 0074/0081: an injected `WorldSource` (e.g. a GenesisWorldSource)
        # overrides the procedural default and persists across profile reloads.
        self._injected_terrain = terrain
        self.terrain: WorldSource | None = (
            terrain if terrain is not None else TerrainModel.from_profile(self.profile)
        )
        self.comms = CommsSubsystem(
            self.profile,
            rng=self.rng,
            position_fn=lambda: (
                self.position.lat,
                self.position.lon,
                self.position.alt_m,
            ),
            terrain=self.terrain,
        )
        self.outbox = CommsOutbox(self.profile, rng=self.rng)
        self._build_dtn_mesh()
        self.position = PositionSubsystem(self.profile, rng=self.rng)
        self.sensors = SensorsSubsystem(self.profile, rng=self.rng)
        self.biometrics = BiometricsSubsystem(self.profile, rng=self.rng)
        self.imu = ImuSubsystem(self.profile, rng=self.rng)
        self.eoir = EoirSubsystem(
            self.profile,
            rng=self.rng,
            ambient_fn=lambda: (self.sensors.temp_c, self.sensors.humidity_pct),
            terrain=self.terrain,
            position_fn=lambda: (
                self.position.lat,
                self.position.lon,
                self.position.alt_m,
            ),
        )
        self.power_est = PowerEstimator(
            initial_soc=self.power.soc_pct,
            initial_voltage=self.power.voltage_v,
        )
        self.apu_est = ApuEstimator()
        self.thermal_est = ThermalKalman(
            initial_junction_c=self.thermal.junction_c,
            initial_enclosure_c=self.thermal.enclosure_c,
        )
        self.compute_est = ComputeKalman(
            initial_load_pct=self.compute.load_pct,
            initial_draw_w=self.compute.draw_w,
        )
        self.storage_est = StorageKalman(
            initial_used_gib=self.storage.used_gib,
            initial_wear_pct=self.storage.wear_pct,
        )
        self.comms_est = CommsParticleFilter(rng=self.rng)
        self.comms_est.update(self.comms.sensor_obs())
        self.state.comms_state, self.state.comms_state_reason = (
            self.comms.derive_state()
        )
        self.position_est = PositionEkf()
        self.position_est.update(self.position.sensor_obs())
        self.sensors_est = EnvironmentalKalman()
        self.sensors_est.update(self.sensors.sensor_obs())
        self.eoir_est = EoirKalman()
        self.eoir_est.update(self.eoir.sensor_obs())
        self.biometrics_est = BiometricsKalman()
        self.biometrics_est.update(self.biometrics.sensor_obs())
        self.state.operator_state, self.state.operator_state_reason = (
            derive_operator(self.biometrics_est.state())
        )

    @property
    def dt_s(self) -> float:
        return 1.0 / float(self.settings.tick_hz)

    def _build_dtn_mesh(self) -> None:
        """Construct the DTN mesh and restore any persisted store (BL-056 inc 4).

        Runs on first boot and on every hot reload. ``dtn_store`` carries the
        persisted store across a true process restart and across a reload; a
        restore is a no-op when the mesh is disabled or nothing is stored.
        """
        mesh = DtnMesh(self.profile, rng=self.rng)
        snapshot = self.dtn_store.load()
        if snapshot is not None:
            mesh.restore(snapshot, now_s=self.state.ts_s)
        self.dtn_mesh = mesh

    def add_tick_hook(self, hook: TickHook) -> None:
        """Register a per-tick observer called with each tick's context (ADR 0040).

        Hooks run at the end of ``tick()``, after the mode has settled, so an
        observer sees the same picture a tool reading the engine would.
        Registering the same callable twice is a no-op.
        """
        if hook not in self._tick_hooks:
            self._tick_hooks.append(hook)

    def remove_tick_hook(self, hook: TickHook) -> None:
        """Deregister a tick observer. Unknown hooks are ignored."""
        if hook in self._tick_hooks:
            self._tick_hooks.remove(hook)

    def _run_tick_hooks(self, ctx: TickContext) -> None:
        """Call every registered hook; a raising hook never kills the tick.

        The tick loop is the safety spine (ADR 0024, ADR 0027): an observer
        bug must degrade the observer, not the plant. Failures are counted on
        ``tick_hook_errors`` (surfaced via ``snapshot()``) so containment
        stays legible rather than silent. The tuple snapshot keeps iteration
        safe when a hook deregisters itself (a session finishing its budget).
        """
        if not self._tick_hooks:
            return
        for hook in tuple(self._tick_hooks):
            try:
                hook(ctx)
            except Exception:  # noqa: BLE001
                self.tick_hook_errors += 1

    def start(self) -> None:
        """Bring-up to the IDLE standby posture. Idempotent. Re-startable after ``stop()``.

        Drives STOWED -> BOOT -> IDLE so a started engine settles in IDLE
        (powered, no active mission) rather than the transient BOOT (ADR 0039).
        Completing boot is plant behaviour, not a supervisory decision: the
        ``ready`` edge is ungated, so it always fires here, while the gated
        operational entries from IDLE (mission / relay / monitoring / c2) stay
        controller-driven.
        """
        if self._started:
            return
        if self.fsm.current is Mode.SHUTDOWN or self.fsm.current is Mode.FAULT:
            prev_reset: Mode = self.fsm.current
            new_reset = self.fsm.transition("reset")
            self._record_transition(prev_reset, "reset", new_reset, reason="boot reset")
        if self.fsm.current is Mode.STOWED:
            prev_boot: Mode = self.fsm.current
            new_boot = self.fsm.transition("boot")
            self._record_transition(prev_boot, "boot", new_boot, reason="boot")
        if self.fsm.current is Mode.BOOT:
            prev_ready: Mode = self.fsm.current
            new_ready = self.fsm.transition("ready")
            self._record_transition(prev_ready, "ready", new_ready, reason="boot complete")
        self._started = True
        self._set_mode(self.fsm.current)
        self.state.ts_s = 0.0
        self.state.tick = 0
        # Per-boot counter, reset with the tick clock: a fresh run's hook
        # health must not inherit a previous run's failures (ADR 0040).
        self.tick_hook_errors = 0

    def reload_profile(self, name: str | None = None) -> dict[str, Any]:
        """Hot-reload the hardware profile from disk (BL-039).

        Re-reads ``profiles/<name>.yaml`` and rebuilds every subsystem
        and estimator against the new curves. FSM mode, tick counter,
        and simulated wall-clock are preserved so a controller can edit
        a panel rating or battery capacity without restarting the
        server.

        Returns a small summary mapping the controller can audit:
        ``{"profile": ..., "rebuilt_subsystems": N, "previous": ...}``.
        The rebuild is atomic: every subsystem is constructed from the new
        profile before any is committed, so a missing or malformed profile
        raises (``FileNotFoundError`` / ``ValueError``, or a constructor error on
        a section that passed top-level validation) with the previous profile and
        subsystems left intact (BL-103 / ADR 0069).
        """
        new_name = (name or self.settings.profile).strip() or self.settings.profile
        new_profile = _load_profile(new_name)
        previous_name = self.settings.profile

        # Build every subsystem from the new profile into locals first (ADR 0019
        # threads the engine RNG into each). If a malformed section crashes a
        # constructor the error propagates with nothing committed, so the engine
        # keeps the previous profile and subsystems rather than tearing into a
        # mixed-generation state (BL-103 / ADR 0069).
        new_pmu = PmuSubsystem.from_profile(new_profile, rng=self.rng)
        new_apu = ApuSubsystem(new_profile, rng=self.rng)
        new_thermal = ThermalSubsystem(new_profile, rng=self.rng)
        new_compute = ComputeSubsystem(new_profile, rng=self.rng)
        new_inference = InferenceSubsystem(
            new_profile, compute=new_compute, rng=self.rng
        )
        new_storage = StorageSubsystem(new_profile, rng=self.rng)
        new_terrain = (
            self._injected_terrain
            if self._injected_terrain is not None
            else TerrainModel.from_profile(new_profile)
        )
        new_comms = CommsSubsystem(
            new_profile,
            rng=self.rng,
            position_fn=lambda: (
                self.position.lat,
                self.position.lon,
                self.position.alt_m,
            ),
            terrain=new_terrain,
        )
        new_outbox = CommsOutbox(new_profile, rng=self.rng)
        new_position = PositionSubsystem(new_profile, rng=self.rng)
        new_sensors = SensorsSubsystem(new_profile, rng=self.rng)
        new_biometrics = BiometricsSubsystem(new_profile, rng=self.rng)
        new_imu = ImuSubsystem(new_profile, rng=self.rng)
        new_eoir = EoirSubsystem(
            new_profile,
            rng=self.rng,
            # Read the new generation's sensor pack: the constructor recomputes
            # immediately, so the closure must not capture the pre-reload sensors.
            ambient_fn=lambda: (new_sensors.temp_c, new_sensors.humidity_pct),
            terrain=new_terrain,
            position_fn=lambda: (
                new_position.lat,
                new_position.lon,
                new_position.alt_m,
            ),
        )

        # Every subsystem constructed: commit the new generation atomically.
        if new_name != self.settings.profile:
            self.settings = self.settings.model_copy(update={"profile": new_name})
        self.profile = new_profile
        self.pmu = new_pmu
        self.power = new_pmu.active_battery
        self.apu = new_apu
        self.thermal = new_thermal
        self.compute = new_compute
        self.inference = new_inference
        self.storage = new_storage
        self.terrain = new_terrain
        self.comms = new_comms
        self.outbox = new_outbox
        self.position = new_position
        self.sensors = new_sensors
        self.biometrics = new_biometrics
        self.imu = new_imu
        self.eoir = new_eoir
        self._build_dtn_mesh()

        self.power_est = PowerEstimator(
            initial_soc=self.power.soc_pct,
            initial_voltage=self.power.voltage_v,
        )
        self.apu_est = ApuEstimator()
        self.thermal_est = ThermalKalman(
            initial_junction_c=self.thermal.junction_c,
            initial_enclosure_c=self.thermal.enclosure_c,
        )
        self.compute_est = ComputeKalman(
            initial_load_pct=self.compute.load_pct,
            initial_draw_w=self.compute.draw_w,
        )
        self.storage_est = StorageKalman(
            initial_used_gib=self.storage.used_gib,
            initial_wear_pct=self.storage.wear_pct,
        )
        self.comms_est = CommsParticleFilter(rng=self.rng)
        self.comms_est.update(self.comms.sensor_obs())
        self.position_est = PositionEkf()
        self.position_est.update(self.position.sensor_obs())
        self.sensors_est = EnvironmentalKalman()
        self.sensors_est.update(self.sensors.sensor_obs())
        self.eoir_est = EoirKalman()
        self.eoir_est.update(self.eoir.sensor_obs())
        self.biometrics_est = BiometricsKalman()
        self.biometrics_est.update(self.biometrics.sensor_obs())

        self.state.comms_state, self.state.comms_state_reason = (
            self.comms.derive_state()
        )
        self.state.operator_state, self.state.operator_state_reason = (
            derive_operator(self.biometrics_est.state())
        )
        # A profile reload rebuilds the physics, so the safety law must restart
        # against it (AUDIT-2026-06-14 RLD-1). A failsafe debounce streak
        # accrued under the old curves is meaningless under the new ones, and a
        # capability claim cached from the old profile must not survive into a
        # read taken before the next tick. Rebuild the arbiter for fresh streaks,
        # actuate the mode entry (which re-applies the posture's compute-load
        # ceiling to the rebuilt subsystem), then recompute the capabilities so
        # the cache reflects the fully-actuated state rather than the un-capped
        # request.
        self._failsafe = FailsafeArbiter(_FAILSAFE_CONDITIONS)
        self._apply_mode_entry(self.state.mode)
        self._refresh_capabilities()

        return {
            "profile": self.settings.profile,
            "previous": previous_name,
            "rebuilt_subsystems": 11,
            "tick": self.state.tick,
            "mode": self.state.mode.value,
        }

    def stop(self) -> None:
        """Cooperative shutdown. Subsystems are not torn down here.

        Idempotent: a second call from SHUTDOWN is a no-op rather than a
        raised ``ValueError``. A controller that calls ``stop`` from a
        state without a defined ``shutdown`` transition (e.g. STOWED)
        gets the same no-op behaviour rather than a crash mid-teardown.
        """
        if not self._started:
            return
        self._started = False
        if self.fsm.can("shutdown"):
            prev = self.fsm.current
            new = self.fsm.transition("shutdown")
            self._record_transition(prev, "shutdown", new, reason="engine.stop")
            self._set_mode(new)
        else:
            self._set_mode(self.fsm.current)

    def request_transition(
        self, trigger: str, *, context: Mapping[str, Any] | None = None
    ) -> tuple[bool, Mode, str]:
        """Drive the FSM with the engine's current safety context.

        Merges caller-supplied ``context`` over the engine-derived defaults
        (thermal headroom, SoC critical threshold). Returns
        ``(ok, mode, reason)``: ``ok=False`` covers both unknown
        transitions and guard refusals so the controller has a single
        observable outcome.
        """
        ctx: dict[str, Any] = self._safety_context()
        if context:
            ctx.update(context)
        prev = self.fsm.current
        try:
            new = self.fsm.transition(trigger, context=ctx)
        except GuardDenied as exc:
            self._audit_safety_checks(trigger, prev, exc.to)
            self._record_transition(
                prev, trigger, exc.to, reason=f"refused: {exc.reason}", denied=True
            )
            return False, self.fsm.current, exc.reason
        except ValueError as exc:
            return False, self.fsm.current, str(exc)
        self._audit_safety_checks(trigger, prev, new)
        self._record_transition(prev, trigger, new, reason="controller")
        self._set_mode(new)
        return True, new, ""

    def _audit_safety_checks(self, trigger: str, frm: Mode, to: Mode) -> None:
        """Mirror each SafetyResult from the last transition to the audit log.

        One ``Tier.SAFETY`` record per gate the FSM evaluated (ADR 0022), so a
        controller can pull every safety event by tier and group by
        ``constraint_id`` without scraping refusal strings. Best-effort: the
        audit sink swallows its own errors, and the pure-Python engine attaches
        no sink, so this is a no-op there.
        """
        if self.audit is None:
            return
        for result in self.fsm.last_safety_checks():
            self.audit.write(
                AuditRecord.from_output(
                    tool="state_transition",
                    tier=int(Tier.SAFETY),
                    args={
                        "trigger": trigger,
                        "from": frm.value,
                        "to": to.value,
                        "constraint_id": result.constraint_id,
                    },
                    output=result.reason,
                    denied=not result.approved,
                    decision_reason=result.reason,
                    safety=_safety_result_to_dict(result),
                )
            )

    def _auto_safe(self) -> None:
        """Drive the FSM toward a safer mode when a failsafe condition trips.

        Evaluated each tick (ADR 0044). The detectors build the raw-active set,
        the :class:`~nous.state.failsafe.FailsafeArbiter` debounces it (the
        operator streak with anti-toggle decay; the device and comms conditions
        instantaneously), and the highest-severity tripped condition fires one
        transition toward safety: its preferred trigger when the table offers an
        edge from the current mode, else the condition's own fallback.

        The operator condition is observed from every mode so its streak tracks
        the label even from IDLE or SAFE, but a transition fires only from an
        operational or impaired mode. From an impaired mode the device and comms
        conditions are out of scope, so only a confirmed operator incapacitation
        can deepen the posture to ``SAFE``. The move is one-way; recovery stays
        controller-gated, so there is no oscillation to debounce.
        """
        mode = self.state.mode
        operational = is_operational(mode)
        ctx = self._safety_context()
        active, projections = self._failsafe_detect(mode, ctx, operational=operational)
        self._failsafe.observe(active)
        if not (operational or is_impaired(mode)):
            return
        condition = self._failsafe.select()
        if condition is None:
            return
        trigger = (
            condition.preferred
            if self.fsm.can(condition.preferred)
            else condition.fallback
        )
        if not self.fsm.can(trigger):
            return
        safety, reason = projections[condition.id]
        prev = self.fsm.current
        try:
            new = self.fsm.transition(trigger, context=ctx)
        except (GuardDenied, ValueError):
            return
        self._audit_auto_safe(trigger, prev, new, safety, reason)
        self._record_transition(
            prev,
            trigger,
            new,
            reason=f"auto-safe: {safety['constraint_id']} -> {trigger}",
        )
        self._set_mode(new)

    def _failsafe_detect(
        self, mode: Mode, ctx: Mapping[str, Any], *, operational: bool
    ) -> tuple[dict[str, bool], dict[str, tuple[dict[str, Any], str]]]:
        """Build this tick's raw-active set and the audit projection per id.

        The operator condition is read from every mode, so its debounce streak
        tracks the label even outside the operational set. The device hazards
        run through the enforcer and the comms condition reads the link label
        only from an operational mode: an impaired mode has no safer edge for
        them, and an enforcer check there would only charge the violation
        counter. The device hazards short-circuit power before thermal, so the
        counter is not charged for a thermal violation the power one pre-empts.
        """
        active: dict[str, bool] = {c.id: False for c in _FAILSAFE_CONDITIONS}
        projections: dict[str, tuple[dict[str, Any], str]] = {}

        if self.state.operator_state is OperatorState.INCAPACITATED:
            reason = self.state.operator_state_reason or "operator incapacitated"
            active[REQ_OPERATOR] = True
            projections[REQ_OPERATOR] = (
                _label_safety(REQ_OPERATOR, reason, ctx),
                reason,
            )

        if operational:
            for constraint_id, candidate_key in (
                (SC_POWER_RESERVE, "soc_pct"),
                (SC_THERMAL_HEADROOM, "thermal_headroom_c"),
            ):
                result = self.safety.check(
                    constraint_id, ctx.get(candidate_key), evidence=ctx
                )
                if not result.approved:
                    active[constraint_id] = True
                    projections[constraint_id] = (
                        _safety_result_to_dict(result),
                        result.reason,
                    )
                    break
            if mode in _LINK_MODES and self.state.comms_state is CommsState.DENIED:
                reason = self.state.comms_state_reason or "comms denied"
                active[REQ_COMMS_LINK] = True
                projections[REQ_COMMS_LINK] = (
                    _label_safety(REQ_COMMS_LINK, reason, ctx),
                    reason,
                )

        return active, projections

    def _set_mode(self, mode: Mode) -> None:
        """Write ``state.mode`` and run the posture's entry action (ADR 0029).

        The single mode-write seam: every path that changes the posture goes
        through here, so ``state.mode`` stays a faithful mirror of
        ``fsm.current`` and the actuation a posture implies has one home.
        """
        self.state.mode = mode
        self._apply_mode_entry(mode)

    def _apply_mode_entry(self, mode: Mode) -> None:
        """Actuate ``mode``: cap (or release) delivered compute load.

        Entering SAFE / LOW_POWER / THERMAL_LIMIT caps the compute subsystem's
        delivered load to the mode's ceiling, so auto-safing genuinely sheds
        load (lower draw, slower drain, less heat) instead of only relabelling
        the posture. Every other mode clears the cap, restoring the
        controller's requested load; the request was preserved under the cap,
        so recovery to IDLE lifts it.
        """
        self.compute.set_mode_load_ceiling(_MODE_LOAD_CEILINGS.get(mode))

    def _audit_auto_safe(
        self,
        trigger: str,
        frm: Mode,
        to: Mode,
        safety: dict[str, Any],
        reason: str,
    ) -> None:
        """Mirror one auto-safing decision to the audit log under Tier.SAFETY."""
        if self.audit is None:
            return
        self.audit.write(
            AuditRecord.from_output(
                tool="auto_safe",
                tier=int(Tier.SAFETY),
                args={
                    "trigger": trigger,
                    "from": frm.value,
                    "to": to.value,
                    "constraint_id": safety.get("constraint_id", ""),
                },
                output=f"auto-safe {frm.value} -> {to.value} ({trigger})",
                denied=True,
                decision_reason=reason,
                safety=safety,
            )
        )

    def _record_transition(
        self,
        frm: Mode,
        trigger: str,
        to: Mode,
        *,
        reason: str = "",
        denied: bool = False,
    ) -> None:
        """Persist a transition to the SQLite log; never raises."""
        prefix = "denied: " if denied else ""
        self.transition_log.append(
            from_mode=frm.value,
            to_mode=to.value,
            trigger=trigger,
            reason=f"{prefix}{reason}"[:256],
        )

    def _safety_context(self) -> dict[str, Any]:
        """Build the safety-gate context from current truth (ADR 0022, 0029).

        The operator and comms labels are the derived FSM state, supplying the
        candidates for the operator-availability and comms-link entry gates
        (ADR 0046). The thermal and SoC readings are subsystem properties
        (always finite floats). The SoC critical reserve is read from the
        profile dict, so it
        is coerced defensively: a non-numeric value, or a ``power`` section that
        is not a mapping at all (both of which ``ProfileModel`` rejects at load,
        but a directly-constructed profile could still carry), omits the key
        rather than crashing the tick loop. With the key absent the SC-8 floor
        has no threshold and fails closed, so a malformed reserve refuses
        operational entry and auto-safes instead of raising.
        """
        power_cfg = self.profile.get("power")
        if power_cfg is None:
            power_cfg = {}
        ctx: dict[str, Any] = {
            "thermal_headroom_c": float(self.thermal.headroom_c),
            "thermal_headroom_threshold_c": float(self.thermal.headroom_threshold_c),
            "soc_pct": float(self.power.soc_pct),
            "operator_state": self.state.operator_state.value,
            "comms_state": self.state.comms_state.value,
        }
        if isinstance(power_cfg, Mapping):
            reserve = _coerce_finite(power_cfg.get("soc_pct_critical_threshold", 5.0))
            if reserve is not None:
                ctx["soc_pct_critical"] = reserve
        return ctx

    def tick(self) -> TickContext:
        """Advance the simulator by one tick. Returns the tick context."""
        if not self._started:
            self.start()
        self.state.tick += 1
        dt = self.dt_s
        self.state.ts_s += dt

        self.compute.set_thermal_throttle(throttling=self.thermal.throttling)
        self.compute.step(dt)
        self.inference.step(dt)
        self.storage.step(dt)
        self.comms.step(dt)
        self.position.step(dt)
        # BL-026: the IMU senses the platform's motion (the position subsystem's
        # commanded speed and heading), differentiated into accel and yaw rate.
        self.imu.set_motion(self.position.speed_mps, self.position.heading_deg)
        self.imu.step(dt)
        self.sensors.step(dt)
        self.biometrics.step(dt)
        # BL-055: the EO/IR payload reads the settled ambient (temp / humidity)
        # to recompute its detection-range envelope, so it steps after sensors.
        self.eoir.step(dt)
        load_w = self.compute.draw_w
        ambient_c = self.sensors.temp_c

        self.apu.step(dt)
        self.thermal.set_load_w(load_w)
        self.thermal.set_ambient_c(ambient_c)
        self.thermal.step(dt)
        # BL-005b: the PMU regulates the APU's offered power into the accepted
        # charge (charge_limit clamp + CC/CV taper) and routes it to the active
        # pack; after the pack steps it arbitrates the dual slots, handing the bus
        # to a charged standby when the active pack is exhausted (no bus collapse).
        accepted_charge_w = self.pmu.regulate_charge(self.apu.total_w)
        self.power.set_load_w(load_w)
        self.power.set_charge_w(accepted_charge_w)
        self.power.set_cell_c(self.thermal.enclosure_c)
        self.power.step(dt)
        self.pmu.step(dt)
        if self.pmu.arbitrate():
            self.power = self.pmu.active_battery

        self.power_est.predict(dt)
        self.power_est.update(self.power.sensor_obs())
        self.apu_est.predict(dt)
        self.apu_est.update(self.apu.sensor_obs())
        self.thermal_est.predict(dt)
        self.thermal_est.update(self.thermal.sensor_obs())
        self.compute_est.predict(dt)
        self.compute_est.update(self.compute.sensor_obs())
        self.storage_est.predict(dt)
        self.storage_est.update(self.storage.sensor_obs())
        self.comms_est.predict(dt)
        self.comms_est.update(self.comms.sensor_obs())
        self.state.comms_state, self.state.comms_state_reason = (
            self.comms.derive_state()
        )
        # Store-and-forward drain (BL-077): deliver queued packages in triage
        # order on any link that recovered this tick, at each link's modelled
        # per-tick capacity. Internal engine machinery, so it runs unguarded
        # like the estimators above -- a raising flush is a bug tests must catch,
        # not a containment case like the external tick hooks.
        self.outbox.flush_tick(self.comms, dt, self.state.ts_s)
        self.dtn_mesh.step(dt, self.state.ts_s)
        if self.dtn_mesh.enabled and self.dtn_mesh.consume_dirty():
            self.dtn_store.save(self.dtn_mesh.snapshot(self.state.ts_s))
        # BL-026: the IMU drives the EKF prediction (stored as the control), then
        # predict propagates the nonlinear model, then GNSS corrects the position.
        self.position_est.update(self.imu.sensor_obs())
        self.position_est.predict(dt)
        self.position_est.update(self.position.sensor_obs())
        self.sensors_est.predict(dt)
        self.sensors_est.update(self.sensors.sensor_obs())
        self.eoir_est.predict(dt)
        self.eoir_est.update(self.eoir.sensor_obs())
        self.biometrics_est.predict(dt)
        self.biometrics_est.update(self.biometrics.sensor_obs())
        self.state.operator_state, self.state.operator_state_reason = (
            derive_operator(self.biometrics_est.state())
        )

        self._refresh_capabilities()
        self._assert_post_tick_finite()
        self._auto_safe()

        ctx = TickContext(
            tick=self.state.tick,
            ts_s=self.state.ts_s,
            dt_s=dt,
            mode=self.state.mode.value,
            profile=self.settings.profile,
        )
        self._run_tick_hooks(ctx)
        return ctx

    def _refresh_capabilities(self) -> None:
        """Refresh ``state.last_capabilities`` from the self-model.

        Imported lazily to keep the engine module free of a self_model
        import at module load (the self_model imports engine through
        ``TYPE_CHECKING`` only).

        The tick loop reads only each claim's ``point`` (the deterministic
        headline), discarding the quantile bands, so it calls ``assess`` in
        the cheap ``mode="gaussian"`` path: ``point`` is mode-invariant
        (pinned by ``test_monte_carlo_and_gaussian_modes_agree_on_point``),
        so this leaves ``state.last_capabilities`` byte-for-byte identical
        while skipping the per-tick Monte Carlo sampling (BL-073). The
        tool-facing reads (``self_model_assess`` / ``self_model_situation``)
        call ``assess`` fresh in the default Monte Carlo mode, so the
        calibrated bands a controller sees are unaffected.
        """
        from .self_model.assess import assess

        a = assess("tick", engine=self, mode="gaussian")
        caps: dict[str, float] = {}
        for cap in (a.endurance, a.thermal_headroom, a.inference_capacity, a.perception_range):
            if cap is not None:
                caps[cap.name] = cap.point
        self.state.last_capabilities = caps

    def _assert_post_tick_finite(self) -> None:
        """Fail loud if a subsystem or estimator emits NaN/Inf or a negative variance.

        Trips at the tick boundary on any non-finite point estimate.
        The covariance ``>= 0`` guard is the catch for the C5-class
        stub-pretending-to-be-real bug: a 1-D variance that goes
        negative is a posterior the filter could not actually compute.
        """
        for name, est in (
            ("power", self.power_est),
            ("apu", self.apu_est),
            ("thermal", self.thermal_est),
            ("compute", self.compute_est),
            ("storage", self.storage_est),
            ("comms", self.comms_est),
            ("position", self.position_est),
            ("sensors", self.sensors_est),
            ("eoir", self.eoir_est),
            ("biometrics", self.biometrics_est),
        ):
            estimate = est.state()
            for key, value in estimate.point.items():
                if not math.isfinite(value):
                    raise RuntimeError(
                        f"non-finite estimate {name}.point.{key}={value!r} "
                        f"at tick {self.state.tick}"
                    )
            for key, raw in estimate.covariance.items():
                if not isinstance(raw, (int, float)):
                    continue
                value = float(raw)
                if not math.isfinite(value) or value < 0.0:
                    raise RuntimeError(
                        f"invalid covariance {name}.covariance.{key}={value!r} "
                        f"at tick {self.state.tick}"
                    )

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe summary of engine state."""
        return {
            "tick": self.state.tick,
            "ts_s": self.state.ts_s,
            "tick_hook_errors": self.tick_hook_errors,
            "mode": self.state.mode.value,
            "operator_state": self.state.operator_state.value,
            "operator_state_reason": self.state.operator_state_reason,
            "comms_state": self.state.comms_state.value,
            "comms_state_reason": self.state.comms_state_reason,
            "profile": self.settings.profile,
            "scenario": self.settings.scenario or None,
            "power": {
                "soc_pct": round(self.power.soc_pct, 3),
                "flag": str(self.power.flag),
            },
            "apu": {
                "total_w": round(self.apu.total_w, 3),
                "fuel_pct": round(self.apu.fuel_pct, 3),
            },
            "thermal": {
                "junction_c": round(self.thermal.junction_c, 3),
                "enclosure_c": round(self.thermal.enclosure_c, 3),
                "headroom_c": round(self.thermal.headroom_c, 3),
                "throttling": self.thermal.throttling,
            },
            "compute": {
                "load_pct": round(self.compute.load_pct, 3),
                "draw_w": round(self.compute.draw_w, 3),
                "throttled": self.compute.throttled,
            },
            "inference": {
                "local_calls": self.inference.local_calls,
                "total_tokens": self.inference.total_tokens,
                "total_energy_j": round(self.inference.total_energy_j, 3),
                "last_latency_s": round(self.inference.last_latency_s, 4),
            },
            "storage": {
                "used_gib": round(self.storage.used_gib, 3),
                "free_gib": round(self.storage.free_gib, 3),
                "wear_pct": round(self.storage.wear_pct, 4),
                "at_capacity": self.storage.at_capacity,
                "worn_out": self.storage.worn_out,
            },
            "comms": {
                "state": self.state.comms_state.value,
                "link_count": len(self.comms.link_ids),
                "connected_links": sum(
                    1 for link in self.comms if link.is_live()
                ),
                "outbox": {
                    "depth": self.outbox.depth(),
                    "queued_bytes": self.outbox.queued_bytes(),
                    "delivered": self.outbox.delivered_total,
                    "expired": self.outbox.expired_total,
                    "dropped_overflow": self.outbox.dropped_overflow_total,
                },
            },
            "position": {
                "lat": round(self.position.lat, 6),
                "lon": round(self.position.lon, 6),
                "alt_m": round(self.position.alt_m, 2),
                "has_fix": self.position.has_fix,
                "dead_reckoning_s": round(self.position.dead_reckoning_s, 2),
            },
            "sensors": {
                "temp_c": round(self.sensors.temp_c, 3),
                "humidity_pct": round(self.sensors.humidity_pct, 3),
                "baro_kpa": round(self.sensors.baro_kpa, 3),
            },
            "eoir": {
                "eo_range_m": round(self.eoir.eo_range_m, 1),
                "ir_range_m": round(self.eoir.ir_range_m, 1),
                "cal_factor": round(self.eoir.cal_factor, 4),
                "obscurant": round(self.eoir.obscurant, 3),
                "illumination": round(self.eoir.illumination, 3),
            },
            "biometrics": {
                "heart_rate_bpm": round(self.biometrics.heart_rate_bpm, 2),
                "core_temp_c": round(self.biometrics.core_temp_c, 3),
                "hydration_pct": round(self.biometrics.hydration_pct, 2),
                "cognitive_load": round(self.biometrics.cognitive_load, 3),
            },
        }


def _json_safe(value: Any) -> Any:
    """Coerce one evidence value to a strict-JSON scalar for the audit line.

    Non-finite floats (NaN, +/-inf) are emitted as their string form rather
    than passed through: the audit log is shipped off-host and replayed by
    strict and cross-language verifiers, and ``NaN``/``Infinity`` are not
    valid JSON. A non-finite candidate already fails its gate closed; this
    only governs how the evidence is recorded.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return value
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return str(value)
    return coerced if math.isfinite(coerced) else str(coerced)


def _safety_result_to_dict(result: SafetyResult) -> dict[str, Any]:
    """Project a :class:`SafetyResult` onto the audit record's ``safety`` field.

    The evidence passes through :func:`nous.audit.redact` before it is
    recorded, the same allowlist the runner applies to tool arguments, so a
    caller-supplied context key cannot smuggle a secret (or a giant string)
    into the safety record that ``request_transition`` mirrors.
    """
    evidence = redact(dict(result.evidence))
    return {
        "constraint_id": result.constraint_id,
        "approved": result.approved,
        "was_clamped": result.was_clamped,
        "violation_type": result.violation_type,
        "value": _json_safe(result.value),
        "evidence": {k: _json_safe(v) for k, v in evidence.items()},
    }


def _label_safety(
    constraint_id: str, detail: str, evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Projection for a label-driven safing decision (operator/comms; ADR 0028).

    Mirrors the shape of :func:`_safety_result_to_dict` so every ``auto_safe``
    audit record reads the same, even when the trigger is a derived state
    label rather than an enforcer constraint. The evidence is redacted on the
    same allowlist as the enforcer path.
    """
    redacted = {k: _json_safe(v) for k, v in redact(dict(evidence)).items()}
    redacted["detail"] = detail
    return {
        "constraint_id": constraint_id,
        "approved": False,
        "was_clamped": False,
        "violation_type": "refused",
        "value": None,
        "evidence": redacted,
    }


def _coerce_finite(value: Any) -> float | None:
    """Coerce ``value`` to a finite, non-bool float, or ``None``.

    Returns ``None`` for a boolean, a non-numeric value, or a non-finite float
    (NaN / infinity), so a safety context can omit the key and let the gate
    fail closed instead of carrying a malformed threshold into the tick loop.
    """
    if isinstance(value, bool):
        return None
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return None
    return coerced if math.isfinite(coerced) else None


def _require_finite_number(value: Any, field_name: str) -> None:
    """Raise ``ValueError`` unless ``value`` is a finite, non-bool number.

    The load-time half of the SC-8 / SC-2 fail-closed posture: a malformed
    safety threshold is refused with a named field so a controller reloading a
    profile sees why it bounced (ADR 0029).
    """
    if _coerce_finite(value) is None:
        raise ValueError(f"{field_name} must be a finite number, got {value!r}")


def _load_profile(name: str) -> Mapping[str, Any]:
    """Load and validate ``profiles/<name>.yaml`` from the source tree."""
    root = Path(__file__).resolve().parents[2] / "profiles" / f"{name}.yaml"
    if not root.exists():
        msg = f"profile YAML not found: {root}"
        raise FileNotFoundError(msg)
    with root.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        msg = f"profile YAML must decode to a mapping: {root}"
        raise ValueError(msg)
    try:
        ProfileModel.model_validate(data)
    except ValidationError as exc:
        detail = "; ".join(
            str(err.get("msg", "")).strip() for err in exc.errors()
        ).strip()
        msg = f"profile YAML failed schema validation: {root}"
        if detail:
            msg = f"{msg}: {detail}"
        raise ValueError(msg) from exc
    return data
