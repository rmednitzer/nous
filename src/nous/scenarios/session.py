"""Stateful scenario session riding the live tick stream (BL-071, ADR 0040).

The one-shot runner (:func:`nous.scenarios.runner.run_scenario`) drives the
engine itself, which means a long scenario blocks the MCP call that started
it. A :class:`ScenarioSession` inverts the control: it registers an engine
tick hook and lets whoever already owns the tick cadence (the process tick
loop under ``nous serve``, a test calling ``engine.tick()``, or the
``tick_advance`` tool) advance the timeline. The session fires injectors as
scenario time elapses and keeps a report the controller can read at any
point through ``scenario_status``.

Pause semantics follow the tier classification (T1, reversible): pausing
freezes the *scenario clock*, never the device. Engine ticks keep flowing
while a session is paused; the session simply stops consuming them, so no
steps fire and the budget does not count down. ``resume`` picks the
timeline up exactly where it stopped. Both are reversible observations on
the engine; the injections a running session applies are the stateful part,
which is why loading a scenario stays T2.

Everything here runs on the single server event loop: the hook is invoked
synchronously from ``Engine.tick()`` and the tools mutate the session
between ticks, so there is no concurrent access to guard.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .loader import Scenario, ScenarioStep
from .runner import ScenarioReport, ScenarioStepRecord, fire_step, skip_step

if TYPE_CHECKING:
    from ..engine import Engine
    from ..types import TickContext

__all__ = ["ScenarioSession", "SessionState", "start_session"]


class SessionState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"


class ScenarioSession:
    """One scenario timeline advancing against the live engine tick stream."""

    def __init__(self, engine: Engine, scenario: Scenario) -> None:
        self.engine = engine
        self.scenario = scenario
        self.state: SessionState = SessionState.RUNNING
        self.records: list[ScenarioStepRecord] = []
        self.ticks_run = 0
        self.elapsed_s = 0.0
        self.started_tick = engine.state.tick
        self.final_snapshot: dict[str, Any] | None = None
        self._pending: list[tuple[int, ScenarioStep]] = list(
            enumerate(scenario.steps_sorted())
        )

    @property
    def active(self) -> bool:
        """True while the session still consumes ticks (running or paused)."""
        return self.state is not SessionState.DONE

    @property
    def steps_fired(self) -> int:
        return sum(1 for r in self.records if r["applied"])

    @property
    def steps_skipped(self) -> int:
        return sum(1 for r in self.records if not r["applied"])

    def start(self) -> None:
        """Fire any ``at_min: 0`` steps and attach to the engine tick stream.

        A no-op on a finished session: completion detached the hook, and
        re-attaching would deliver ticks the DONE guard silently discards.
        """
        if self.state is SessionState.DONE:
            return
        self._fire_due(0.0)
        self.engine.add_tick_hook(self.on_tick)

    def on_tick(self, ctx: TickContext) -> None:
        """Consume one engine tick: advance the scenario clock, fire due steps.

        Registered as an engine tick hook; called after the tick has settled.
        A paused session ignores the tick entirely (the scenario clock is
        frozen; the device keeps living).
        """
        if self.state is not SessionState.RUNNING:
            return
        self.ticks_run += 1
        self.elapsed_s += float(ctx.dt_s)
        self._fire_due(self.elapsed_s / 60.0)
        if self.ticks_run >= self.scenario.tick_budget:
            self._finish()

    def pause(self) -> tuple[bool, str]:
        """Freeze the scenario clock. Idempotent; refuses once done."""
        if self.state is SessionState.DONE:
            return False, "session is done; scenario_reset clears it"
        self.state = SessionState.PAUSED
        return True, ""

    def resume(self) -> tuple[bool, str]:
        """Unfreeze the scenario clock. Idempotent; refuses once done."""
        if self.state is SessionState.DONE:
            return False, "session is done; scenario_reset clears it"
        self.state = SessionState.RUNNING
        return True, ""

    def close(self) -> None:
        """Detach from the engine without altering applied injections."""
        self.engine.remove_tick_hook(self.on_tick)

    def status(self, *, include_records: bool = True) -> dict[str, Any]:
        """JSON-safe progress read for the ``scenario_status`` tool (T0)."""
        next_step: dict[str, Any] | None = None
        if self._pending:
            idx, step = self._pending[0]
            next_step = {"index": idx, "at_min": step.at_min, "action": step.action}
        payload: dict[str, Any] = {
            "state": self.state.value,
            "name": self.scenario.name,
            "profile": self.scenario.profile,
            "tick_budget": self.scenario.tick_budget,
            "ticks_run": self.ticks_run,
            "elapsed_min": round(self.elapsed_s / 60.0, 4),
            "started_tick": self.started_tick,
            "engine_tick": self.engine.state.tick,
            "steps_total": len(self.scenario.steps),
            "steps_fired": self.steps_fired,
            "steps_skipped": self.steps_skipped,
            "steps_pending": len(self._pending),
            "next_step": next_step,
        }
        if include_records:
            payload["records"] = list(self.records)
        return payload

    def report(self) -> ScenarioReport:
        """Final report in the exact shape ``run_scenario`` returns.

        The snapshot is the one captured when the budget completed, so the
        report describes the device at scenario end even if the engine has
        ticked on since (it always does under the live loop). Before
        completion the snapshot is the live one.
        """
        snapshot = self.final_snapshot
        if snapshot is None:
            snapshot = self.engine.snapshot()
        return ScenarioReport(
            scenario=self.scenario,
            ticks_run=self.ticks_run,
            records=self.records,
            snapshot=snapshot,
        )

    def _fire_due(self, elapsed_min: float) -> None:
        while self._pending and self._pending[0][1].at_min <= elapsed_min:
            idx, step = self._pending.pop(0)
            self.records.append(fire_step(self.engine, idx, step))

    def _finish(self) -> None:
        for idx, step in self._pending:
            self.records.append(skip_step(self.engine, idx, step))
        self._pending.clear()
        self.final_snapshot = self.engine.snapshot()
        self.state = SessionState.DONE
        self.close()


def start_session(engine: Engine, scenario: Scenario) -> ScenarioSession:
    """Start ``scenario`` as a live session against ``engine``.

    Mirrors ``run_scenario``'s t=0 boundary: the engine is started
    idempotently and any ``at_min: 0`` steps fire before the first tick the
    session consumes, so the two execution surfaces agree on when a
    zero-minute injection lands.

    One session per engine is the caller's contract (the tool layer holds
    it on ``Nous.scenario_session``); two concurrent sessions would each
    consume the same tick stream and fire interleaved injections.
    """
    engine.start()
    session = ScenarioSession(engine, scenario)
    session.start()
    return session
