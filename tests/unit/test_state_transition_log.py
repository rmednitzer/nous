"""Tests for the BL-017 state_history SQLite persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.db import StateTransitionLog, init_db
from nous.engine import Engine
from nous.state.machine import Mode


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "state.db"


@pytest.fixture
def transition_log(db_path: Path) -> StateTransitionLog:
    engine = init_db(f"sqlite:///{db_path}")
    return StateTransitionLog(engine)


def test_append_then_tail_returns_rows(transition_log: StateTransitionLog) -> None:
    transition_log.append(from_mode="stowed", to_mode="boot", trigger="boot")
    transition_log.append(from_mode="boot", to_mode="idle", trigger="ready")
    rows = transition_log.tail(10)
    assert len(rows) == 2
    assert rows[0].trigger == "boot"
    assert rows[1].trigger == "ready"


def test_tail_returns_oldest_first(transition_log: StateTransitionLog) -> None:
    for trig in ("boot", "ready", "mission"):
        transition_log.append(
            from_mode="x", to_mode="y", trigger=trig
        )
    rows = transition_log.tail(2)
    assert len(rows) == 2
    assert [r.trigger for r in rows] == ["ready", "mission"]


def test_no_engine_means_no_op() -> None:
    log = StateTransitionLog(None)
    log.append(from_mode="a", to_mode="b", trigger="x")
    assert log.tail(5) == []
    assert log.append_failures == 0


def test_engine_persists_boot_transition(
    tmp_nous_home: Path, db_path: Path
) -> None:
    engine = init_db(f"sqlite:///{db_path}")
    log = StateTransitionLog(engine)
    e = Engine(transition_log=log)
    e.start()
    rows = log.tail(10)
    triggers = [r.trigger for r in rows]
    assert "boot" in triggers


def test_engine_persists_request_transition(
    tmp_nous_home: Path, db_path: Path
) -> None:
    engine = init_db(f"sqlite:///{db_path}")
    log = StateTransitionLog(engine)
    e = Engine(transition_log=log)
    e.start()
    e.request_transition("ready")
    ok, _, _ = e.request_transition(
        "mission",
        context={"thermal_headroom_c": 30.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert ok
    rows = log.tail(10)
    triggers = [r.trigger for r in rows]
    assert "mission" in triggers
    mission_row = next(r for r in rows if r.trigger == "mission")
    assert mission_row.to_mode == Mode.MISSION.value


def test_guard_denied_recorded_with_denied_reason(
    tmp_nous_home: Path, db_path: Path
) -> None:
    engine = init_db(f"sqlite:///{db_path}")
    log = StateTransitionLog(engine)
    e = Engine(transition_log=log)
    e.start()
    e.request_transition("ready")
    ok, _, _ = e.request_transition(
        "mission",
        context={"thermal_headroom_c": 0.5, "thermal_headroom_threshold_c": 5.0},
    )
    assert ok is False
    rows = log.tail(10)
    refusal = next(
        (r for r in rows if r.trigger == "mission" and r.reason.startswith("denied:")),
        None,
    )
    assert refusal is not None
