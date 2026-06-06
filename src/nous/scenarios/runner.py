"""Scenario runner: drive the engine through a scenario timeline (BL-014).

The runner advances the engine tick by tick. When the simulated
elapsed time crosses a step's ``at_min``, the runner fires the
injector and records the outcome on a per-run report. The report is
JSON-safe so a caller (CLI, scenario MCP tool) can stream it back to
the controller.

Determinism: the runner uses ``engine.state.ts_s`` as the clock so
two runs of the same scenario against the same profile and tick rate
produce the same outputs. No wall-clock sleeps; the runner is
suitable for unit tests and for the showcase telemetry script.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .injectors import apply_injection
from .loader import Scenario, ScenarioStep

if TYPE_CHECKING:
    from ..engine import Engine

__all__ = ["ScenarioReport", "ScenarioStepRecord", "run_scenario"]


class ScenarioStepRecord(dict[str, Any]):
    """One row of the scenario report; behaves as a JSON-safe dict."""

    def __init__(
        self,
        *,
        index: int,
        at_min: float,
        ts_s: float,
        tick: int,
        action: str,
        applied: bool,
        result: Any = None,
        error: str = "",
        args: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            index=index,
            at_min=at_min,
            ts_s=ts_s,
            tick=tick,
            action=action,
            applied=applied,
            result=result,
            error=error,
            args=dict(args or {}),
        )


class ScenarioReport(dict[str, Any]):
    """Run report; behaves as a JSON-safe dict."""

    def __init__(
        self,
        *,
        scenario: Scenario,
        ticks_run: int,
        records: list[ScenarioStepRecord],
        snapshot: dict[str, Any],
    ) -> None:
        super().__init__(
            name=scenario.name,
            profile=scenario.profile,
            tick_budget=scenario.tick_budget,
            steps_total=len(scenario.steps),
            steps_fired=sum(1 for r in records if r["applied"]),
            steps_skipped=sum(1 for r in records if not r["applied"]),
            ticks_run=ticks_run,
            records=records,
            snapshot=snapshot,
        )


def run_scenario(engine: Engine, scenario: Scenario) -> ScenarioReport:
    """Drive ``engine`` through ``scenario``. Returns a structured report.

    The runner starts the engine idempotently (``engine.start()``) but does
    not own the stop/shutdown lifecycle; the caller does, so the runner stays
    composable with the FastMCP lifespan and the CLI's ``nous scenario``
    subcommand. ``start()`` completes bring-up to IDLE (ADR 0039), so the
    canonical scenarios (which start with a mission / relay / monitoring / c2
    trigger from IDLE) admit cleanly.

    Tick accounting is relative to this run: ``tick_budget`` is the
    number of ticks the runner will advance, measured from the
    engine's current tick. ``ticks_run`` on the report is the same
    delta -- a long-lived engine that has already advanced past
    ``tick_budget`` does not short-circuit the run.

    Zero-minute steps fire before the first ``engine.tick()`` so a
    scenario whose first step is ``at_min: 0`` sees the injection
    applied at the run's t=0 boundary rather than one tick late.
    """
    engine.start()  # start() completes bring-up to IDLE (ADR 0039)

    steps = scenario.steps_sorted()
    pending: list[tuple[int, ScenarioStep]] = list(enumerate(steps))
    records: list[ScenarioStepRecord] = []

    start_ts = engine.state.ts_s
    start_tick = engine.state.tick

    def _fire_due(elapsed_min: float) -> None:
        while pending and pending[0][1].at_min <= elapsed_min:
            idx, step = pending.pop(0)
            outcome = apply_injection(engine, step.action, step.args)
            records.append(
                ScenarioStepRecord(
                    index=idx,
                    at_min=step.at_min,
                    ts_s=engine.state.ts_s,
                    tick=engine.state.tick,
                    action=step.action,
                    applied=bool(outcome.get("applied", False)),
                    result=outcome.get("result"),
                    error=str(outcome.get("error", "")),
                    args=dict(step.args),
                )
            )

    _fire_due(0.0)

    for ticks_run_idx, _ in enumerate(range(scenario.tick_budget), start=1):
        engine.tick()
        elapsed_min = (engine.state.ts_s - start_ts) / 60.0
        _fire_due(elapsed_min)
        if not pending and ticks_run_idx >= scenario.tick_budget:
            break

    for idx, step in pending:
        records.append(
            ScenarioStepRecord(
                index=idx,
                at_min=step.at_min,
                ts_s=engine.state.ts_s,
                tick=engine.state.tick,
                action=step.action,
                applied=False,
                error="tick budget exhausted before scheduled time",
                args=dict(step.args),
            )
        )

    return ScenarioReport(
        scenario=scenario,
        ticks_run=engine.state.tick - start_tick,
        records=records,
        snapshot=engine.snapshot(),
    )
