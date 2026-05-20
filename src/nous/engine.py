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
from .state.comms_state import CommsState
from .state.machine import Mode, StateMachine
from .state.operator_state import OperatorState
from .types import TickContext

__all__ = ["Engine", "EngineState"]


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
        self.state.ts_s += self.dt_s
        ctx = TickContext(
            tick=self.state.tick,
            ts_s=self.state.ts_s,
            dt_s=self.dt_s,
            mode=self.state.mode.value,
            profile=self.settings.profile,
        )
        # Subsystem step, estimator update, self-model refresh land in L1.
        # The scaffold's tick is a pure no-op apart from clock advance.
        return ctx

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
