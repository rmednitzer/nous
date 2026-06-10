"""Stateful scenario session semantics (BL-071, ADR 0040).

The session rides the engine tick hook: whoever owns the tick cadence
advances the timeline. Pause freezes the scenario clock (the device keeps
ticking); the budget and step thresholds count only consumed ticks, so the
session's report matches what the one-shot runner would have produced for
the same scenario.
"""

from __future__ import annotations

from typing import Any

import pytest

from nous.engine import Engine
from nous.scenarios import (
    Scenario,
    SessionState,
    load_scenario,
    run_scenario,
    start_session,
)
from nous.scenarios.injectors import INJECTORS


def _scenario(
    steps: list[dict[str, Any]], *, tick_budget: int = 6, name: str = "session-test"
) -> Scenario:
    return load_scenario(
        {
            "meta": {"name": name},
            "tick_budget": tick_budget,
            "steps": steps,
        }
    )


def _ticks_for_minutes(engine: Engine, minutes: float) -> int:
    return round(minutes * 60.0 / engine.dt_s)


def test_zero_minute_step_fires_before_first_tick(engine: Engine) -> None:
    session = start_session(
        engine,
        _scenario([{"at_min": 0, "action": "inject_compute", "args": {"load_pct": 40}}]),
    )

    assert session.state is SessionState.RUNNING
    assert len(session.records) == 1
    assert session.records[0]["applied"] is True
    assert session.ticks_run == 0


def test_step_fires_when_scenario_clock_crosses_threshold(engine: Engine) -> None:
    # At the default 2 Hz, 0.025 min = 1.5 s = 3 ticks.
    at_min = 0.025
    need = _ticks_for_minutes(engine, at_min)
    session = start_session(
        engine,
        _scenario(
            [{"at_min": at_min, "action": "inject_compute", "args": {"load_pct": 55}}],
            tick_budget=need + 4,
        ),
    )

    for _ in range(need - 1):
        engine.tick()
    assert session.records == []

    engine.tick()
    assert len(session.records) == 1
    assert session.records[0]["applied"] is True
    assert session.ticks_run == need


def test_pause_freezes_scenario_clock_not_the_device(engine: Engine) -> None:
    session = start_session(
        engine,
        _scenario(
            [{"at_min": 0.01, "action": "inject_compute", "args": {"load_pct": 70}}],
            tick_budget=10,
        ),
    )
    ok, _ = session.pause()
    assert ok and session.state.value == "paused"

    device_tick_before = engine.state.tick
    for _ in range(8):
        engine.tick()

    # The device lived through eight ticks; the scenario consumed none.
    assert engine.state.tick == device_tick_before + 8
    assert session.ticks_run == 0
    assert session.records == []

    ok, _ = session.resume()
    assert ok and session.state.value == "running"
    for _ in range(2):
        engine.tick()
    assert session.ticks_run == 2
    assert len(session.records) == 1


def test_budget_completion_marks_done_and_detaches(engine: Engine) -> None:
    # 4 ticks = 2 s; a step at 1 minute is unreachable and must be recorded
    # as skipped exactly like the one-shot runner records it.
    session = start_session(
        engine,
        _scenario(
            [{"at_min": 1.0, "action": "inject_compute", "args": {"load_pct": 30}}],
            tick_budget=4,
        ),
    )
    for _ in range(4):
        engine.tick()

    assert session.state is SessionState.DONE
    assert session.active is False
    assert session.ticks_run == 4
    assert len(session.records) == 1
    assert session.records[0]["applied"] is False
    assert session.records[0]["error"] == "tick budget exhausted before scheduled time"

    # Detached: further device ticks no longer advance the scenario.
    engine.tick()
    assert session.ticks_run == 4


def test_done_report_matches_run_scenario_shape(engine: Engine) -> None:
    steps = [
        {"at_min": 0, "action": "inject_compute", "args": {"load_pct": 25}},
        {"at_min": 99.0, "action": "inject_compute", "args": {"load_pct": 60}},
    ]
    session = start_session(engine, _scenario(steps, tick_budget=3))
    for _ in range(3):
        engine.tick()
    session_report = session.report()

    one_shot = run_scenario(Engine(settings=engine.settings), _scenario(steps, tick_budget=3))

    assert set(session_report) == set(one_shot)
    assert session_report["steps_total"] == one_shot["steps_total"] == 2
    assert session_report["steps_fired"] == one_shot["steps_fired"] == 1
    assert session_report["steps_skipped"] == one_shot["steps_skipped"] == 1
    assert session_report["ticks_run"] == one_shot["ticks_run"] == 3


def test_start_is_a_no_op_on_a_finished_session(engine: Engine) -> None:
    session = start_session(engine, _scenario([], tick_budget=1))
    engine.tick()
    assert session.state is SessionState.DONE

    # Re-attaching a finished session would deliver ticks its DONE guard
    # silently discards; start() refuses instead.
    session.start()
    engine.tick()
    assert session.ticks_run == 1


def test_report_snapshot_is_frozen_at_completion(engine: Engine) -> None:
    session = start_session(engine, _scenario([], tick_budget=2))
    engine.tick()
    engine.tick()
    assert session.state is SessionState.DONE
    completion_tick = session.report()["snapshot"]["tick"]

    for _ in range(5):
        engine.tick()
    assert session.report()["snapshot"]["tick"] == completion_tick
    assert engine.state.tick == completion_tick + 5


def test_pause_and_resume_refused_once_done(engine: Engine) -> None:
    session = start_session(engine, _scenario([], tick_budget=1))
    engine.tick()
    assert session.state is SessionState.DONE

    ok, reason = session.pause()
    assert not ok and "done" in reason
    ok, reason = session.resume()
    assert not ok and "done" in reason


def test_close_detaches_a_live_session(engine: Engine) -> None:
    session = start_session(engine, _scenario([], tick_budget=10))
    engine.tick()
    assert session.ticks_run == 1

    session.close()
    engine.tick()
    assert session.ticks_run == 1
    # Close is detachment, not completion: the state is honest about the
    # timeline never having finished.
    assert session.state is SessionState.RUNNING


def test_status_reports_progress_and_next_step(engine: Engine) -> None:
    session = start_session(
        engine,
        _scenario(
            [
                {"at_min": 0, "action": "inject_compute", "args": {"load_pct": 20}},
                {"at_min": 5.0, "action": "inject_compute", "args": {"load_pct": 80}},
            ],
            tick_budget=600,
        ),
    )
    engine.tick()
    status = session.status()

    assert status["state"] == "running"
    assert status["name"] == "session-test"
    assert status["tick_budget"] == 600
    assert status["ticks_run"] == 1
    assert status["steps_total"] == 2
    assert status["steps_fired"] == 1
    assert status["steps_pending"] == 1
    assert status["next_step"] == {"index": 1, "at_min": 5.0, "action": "inject_compute"}
    assert status["elapsed_min"] == round(engine.dt_s / 60.0, 4)


def test_raising_injector_is_recorded_not_propagated(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(engine: Engine, args: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("injector bug")

    monkeypatch.setitem(INJECTORS, "boom", _boom)
    session = start_session(
        engine,
        _scenario(
            [
                {"at_min": 0, "action": "boom"},
                {"at_min": 0.01, "action": "inject_compute", "args": {"load_pct": 35}},
            ],
            tick_budget=5,
        ),
    )
    for _ in range(5):
        engine.tick()

    assert session.state is SessionState.DONE
    assert engine.tick_hook_errors == 0
    boom, follow = session.records[0], session.records[1]
    assert boom["applied"] is False
    assert "RuntimeError" in boom["error"]
    assert follow["applied"] is True
