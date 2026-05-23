"""Orchestrator: holds subsystems, estimators, and the self-model.

The :class:`Engine` is the headless heart of the simulator. ``tick()``
advances every subsystem by ``dt``, feeds each estimator its observation,
and asks the self-model to refresh its capability claims. The engine is
usable without an MCP server, which keeps the tick loop testable in pure
Python.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import Settings, get_settings
from .estimators.apu import ApuEstimator
from .estimators.compute import ComputeKalman
from .estimators.power import PowerEstimator
from .estimators.storage import StorageKalman
from .estimators.thermal import ThermalKalman
from .state.comms_state import CommsState
from .state.machine import GuardDenied, Mode, StateMachine
from .state.operator_state import OperatorState
from .subsystems.apu import ApuSubsystem
from .subsystems.compute import ComputeSubsystem
from .subsystems.inference import InferenceSubsystem
from .subsystems.power import PowerSubsystem
from .subsystems.storage import StorageSubsystem
from .subsystems.thermal import ThermalSubsystem
from .types import TickContext

__all__ = ["Engine", "EngineState"]


_DEFAULT_AMBIENT_C = 25.0


@dataclass
class EngineState:
    tick: int = 0
    ts_s: float = 0.0
    mode: Mode = Mode.STOWED
    operator_state: OperatorState = OperatorState.NOMINAL
    comms_state: CommsState = CommsState.CONNECTED
    last_capabilities: dict[str, float] = field(default_factory=dict)


class Engine:
    """Tick-driven simulator orchestrator."""

    def __init__(
        self,
        settings: Settings | None = None,
        profile: Mapping[str, Any] | None = None,
        scenario: Mapping[str, Any] | None = None,
    ) -> None:
        self.settings: Settings = settings or get_settings()
        self.profile: Mapping[str, Any] = profile or _load_profile(self.settings.profile)
        self.scenario: Mapping[str, Any] | None = scenario
        self.fsm = StateMachine()
        self.state = EngineState(mode=self.fsm.current)
        self._started = False
        self._wall_start = 0.0

        self.power = PowerSubsystem(self.profile)
        self.apu = ApuSubsystem(self.profile)
        self.thermal = ThermalSubsystem(self.profile)
        self.compute = ComputeSubsystem(self.profile)
        self.inference = InferenceSubsystem(self.profile, compute=self.compute)
        self.storage = StorageSubsystem(self.profile)
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

    @property
    def dt_s(self) -> float:
        return 1.0 / float(self.settings.tick_hz)

    def start(self) -> None:
        """Boot transition. Idempotent. Re-startable after ``stop()``."""
        if self._started:
            return
        if self.fsm.current is Mode.SHUTDOWN or self.fsm.current is Mode.FAULT:
            self.fsm.transition("reset")
        if self.fsm.current is Mode.STOWED:
            self.fsm.transition("boot")
        self._started = True
        self._wall_start = time.monotonic()
        self.state.mode = self.fsm.current
        self.state.ts_s = 0.0
        self.state.tick = 0

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
            self.state.mode = self.fsm.transition("shutdown")
        else:
            self.state.mode = self.fsm.current

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
        try:
            new = self.fsm.transition(trigger, context=ctx)
        except GuardDenied as exc:
            return False, self.fsm.current, exc.reason
        except ValueError as exc:
            return False, self.fsm.current, str(exc)
        self.state.mode = new
        return True, new, ""

    def _safety_context(self) -> dict[str, Any]:
        power_cfg = self.profile.get("power") or {}
        return {
            "thermal_headroom_c": float(self.thermal.headroom_c),
            "thermal_headroom_threshold_c": float(
                self.thermal.headroom_threshold_c
            ),
            "soc_pct": float(self.power.soc_pct),
            "soc_pct_critical": float(
                power_cfg.get("soc_pct_critical_threshold", 5.0)
            ),
        }

    def tick(self) -> TickContext:
        """Advance the simulator by one tick. Returns the tick context."""
        if not self._started:
            self.start()
        self.state.tick += 1
        dt = self.dt_s
        self.state.ts_s += dt

        ambient_c = self._default_ambient_c()

        self.compute.set_thermal_throttle(throttling=self.thermal.throttling)
        self.compute.step(dt)
        self.inference.step(dt)
        self.storage.step(dt)
        load_w = self.compute.draw_w

        self.apu.step(dt)
        self.thermal.set_load_w(load_w)
        self.thermal.set_ambient_c(ambient_c)
        self.thermal.step(dt)
        self.power.set_load_w(load_w)
        self.power.set_charge_w(self.apu.total_w)
        self.power.set_cell_c(self.thermal.enclosure_c)
        self.power.step(dt)

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

        ctx = TickContext(
            tick=self.state.tick,
            ts_s=self.state.ts_s,
            dt_s=dt,
            mode=self.state.mode.value,
            profile=self.settings.profile,
        )
        return ctx

    def _default_ambient_c(self) -> float:
        """Ambient temperature input for the thermal subsystem.

        Until a scenario injector drives ambient (BL-014), the engine
        uses ``profile.thermal.ambient_c_default``. The two-state
        thermal model in :mod:`nous.subsystems.thermal` integrates from
        this baseline and the compute load to produce the enclosure
        temperature that drives the battery's thermal derate.
        """
        thermal_cfg = self.profile.get("thermal") or {}
        return float(thermal_cfg.get("ambient_c_default", _DEFAULT_AMBIENT_C))

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe summary of engine state."""
        return {
            "tick": self.state.tick,
            "ts_s": self.state.ts_s,
            "mode": self.state.mode.value,
            "operator_state": self.state.operator_state.value,
            "comms_state": self.state.comms_state.value,
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
        }


def _load_profile(name: str) -> Mapping[str, Any]:
    """Load ``profiles/<name>.yaml`` from the source tree or fall back to defaults."""
    root = Path(__file__).resolve().parents[2] / "profiles" / f"{name}.yaml"
    if root.exists():
        with root.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict):
            return data
    return {"name": name, "source": "default-fallback"}
