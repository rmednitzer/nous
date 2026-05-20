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
from .estimators.power import PowerEstimator
from .state.comms_state import CommsState
from .state.machine import Mode, StateMachine
from .state.operator_state import OperatorState
from .subsystems.apu import ApuSubsystem
from .subsystems.power import PowerSubsystem
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
        self.power_est = PowerEstimator(
            initial_soc=self.power.soc_pct,
            initial_voltage=self.power.voltage_v,
        )
        self.apu_est = ApuEstimator()

    @property
    def dt_s(self) -> float:
        return 1.0 / float(self.settings.tick_hz)

    def start(self) -> None:
        """Boot transition. Idempotent."""
        if self._started:
            return
        self._started = True
        self._wall_start = time.monotonic()
        self.state.mode = self.fsm.transition("boot")
        self.state.ts_s = 0.0

    def stop(self) -> None:
        """Cooperative shutdown. Subsystems are not torn down here."""
        if not self._started:
            return
        self._started = False
        self.state.mode = self.fsm.transition("shutdown")

    def tick(self) -> TickContext:
        """Advance the simulator by one tick. Returns the tick context."""
        if not self._started:
            self.start()
        self.state.tick += 1
        dt = self.dt_s
        self.state.ts_s += dt

        load_w = self._default_load_w()
        cell_c = self._default_cell_c()

        self.apu.step(dt)
        self.power.set_load_w(load_w)
        self.power.set_charge_w(self.apu.total_w)
        self.power.set_cell_c(cell_c)
        self.power.step(dt)

        self.power_est.predict(dt)
        self.power_est.update(self.power.sensor_obs())
        self.apu_est.predict(dt)
        self.apu_est.update(self.apu.sensor_obs())

        ctx = TickContext(
            tick=self.state.tick,
            ts_s=self.state.ts_s,
            dt_s=dt,
            mode=self.state.mode.value,
            profile=self.settings.profile,
        )
        return ctx

    def _default_load_w(self) -> float:
        """Idle compute draw from the profile.

        The compute subsystem (BL-007) lands later and will report a real
        load. Until then, the engine uses ``profile.compute.draw_w_idle``
        so the battery and APU loops behave plausibly under the default
        scenario.
        """
        compute_cfg = self.profile.get("compute") or {}
        return float(compute_cfg.get("draw_w_idle", 0.0))

    def _default_cell_c(self) -> float:
        """Ambient temperature fallback for the battery's thermal derate."""
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
