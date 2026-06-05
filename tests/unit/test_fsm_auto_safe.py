"""Condition-driven auto-safing on tick (ADR 0027).

PR1 wired the entry gates; this is the tick-loop control law that closes the
H-2/H-8 "sustains" gap. The engine, from an operational mode, drives the FSM
toward a safer mode when SC-2 or SC-8 is violated, one transition per tick,
toward safety only. These tests pin the target mapping (preferred trigger vs
degrade fallback), the operational-mode gate, the power-before-thermal
priority, the Tier.SAFETY audit mirror, and that recovery stays
controller-gated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nous.audit import AuditLogger
from nous.db import StateTransitionLog, init_db
from nous.engine import Engine
from nous.policy import Tier
from nous.state.comms_state import CommsState
from nous.state.machine import Mode, is_operational
from nous.state.operator_state import OperatorState

_OK_ENTRY = {
    "thermal_headroom_c": 30.0,
    "thermal_headroom_threshold_c": 5.0,
    "soc_pct": 80.0,
    "soc_pct_critical": 5.0,
}


def _engine_in(mode_trigger: str, *, audit_path: str | None = None) -> Engine:
    """Boot an engine and drive it to the operational mode under test."""
    eng = Engine(audit=AuditLogger(audit_path) if audit_path else None)
    eng.start()
    eng.request_transition("ready")
    ok, _mode, _reason = eng.request_transition(mode_trigger, context=_OK_ENTRY)
    assert ok
    return eng


def test_auto_safe_power_from_mission_enters_low_power(tmp_nous_home: Path) -> None:
    eng = _engine_in("mission")
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.state.mode is Mode.LOW_POWER


def test_auto_safe_thermal_from_mission_enters_thermal_limit(tmp_nous_home: Path) -> None:
    eng = _engine_in("mission")
    eng.thermal.set_junction_c(84.0)  # ~1C headroom, below the 5C threshold
    eng._auto_safe()
    assert eng.state.mode is Mode.THERMAL_LIMIT


@pytest.mark.parametrize("trigger", ["relay", "monitoring", "c2"])
def test_auto_safe_falls_back_to_degrade_without_specific_edge(
    tmp_nous_home: Path, trigger: str
) -> None:
    # RELAY/MONITORING/C2 have no low_power edge, so a power violation
    # degrades them instead (ADR 0027 fallback).
    eng = _engine_in(trigger)
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.state.mode is Mode.DEGRADED


def test_auto_safe_is_no_op_when_healthy(tmp_nous_home: Path) -> None:
    eng = _engine_in("mission")
    eng._auto_safe()
    assert eng.state.mode is Mode.MISSION


def test_auto_safe_does_not_fire_from_non_operational_mode(tmp_nous_home: Path) -> None:
    # IDLE is not an operational mode; a critical pack there must not move
    # the FSM (and IDLE has no safer edge to take anyway).
    eng = Engine()
    eng.start()
    eng.request_transition("ready")
    assert eng.state.mode is Mode.IDLE
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.state.mode is Mode.IDLE


def test_auto_safe_power_takes_priority_over_thermal(tmp_nous_home: Path) -> None:
    # Both constraints violated: power is checked first, so the device sheds
    # load via LOW_POWER rather than THERMAL_LIMIT.
    eng = _engine_in("mission")
    eng.power.set_soc_pct(2.0)
    eng.thermal.set_junction_c(84.0)
    eng._auto_safe()
    assert eng.state.mode is Mode.LOW_POWER


def test_auto_safe_fires_through_tick(tmp_nous_home: Path) -> None:
    # The tick loop is the real caller. A pack just below critical crosses
    # the threshold within one tick and the returned context reflects it.
    eng = _engine_in("mission")
    eng.power.set_soc_pct(4.0)
    ctx = eng.tick()
    assert eng.state.mode is Mode.LOW_POWER
    assert ctx.mode == Mode.LOW_POWER.value
    # One transition per tick: a subsequent tick from LOW_POWER does not move.
    eng.tick()
    assert eng.state.mode is Mode.LOW_POWER


def test_auto_safe_increments_posture(tmp_nous_home: Path) -> None:
    eng = _engine_in("mission")
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.safety.violation_count("SC-8") == 1


def test_auto_safe_writes_tier_safety_audit(tmp_nous_home: Path) -> None:
    log_path = str(tmp_nous_home / "audit.jsonl")
    eng = _engine_in("mission", audit_path=log_path)
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    records = [
        rec
        for line in Path(log_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
        for rec in [json.loads(line)]
        if rec.get("tool") == "auto_safe"
    ]
    assert len(records) == 1
    rec = records[0]
    assert rec["tier"] == int(Tier.SAFETY)
    assert rec["denied"] is True
    assert rec["args"]["from"] == Mode.MISSION.value
    assert rec["args"]["to"] == Mode.LOW_POWER.value
    assert rec["safety"]["constraint_id"] == "SC-8"


def test_auto_safe_recovery_is_controller_gated(tmp_nous_home: Path) -> None:
    eng = _engine_in("mission")
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.state.mode is Mode.LOW_POWER
    # The engine never auto-recovers; recovery is a controller call that the
    # same enforcer re-checks, so it is refused while the pack is critical.
    ok, mode, reason = eng.request_transition("recover")
    assert not ok
    assert mode is Mode.LOW_POWER
    assert "SC-8" in reason
    # Once the pack recovers, the controller can recover (thermal is healthy).
    eng.power.set_soc_pct(80.0)
    ok, mode, _reason = eng.request_transition("recover")
    assert ok
    assert mode is Mode.MISSION


def test_auto_safe_operator_incapacitated_enters_safe(tmp_nous_home: Path) -> None:
    # ADR 0028: an incapacitated operator takes the full safe posture, using
    # the direct safe edge the reachability work added.
    eng = _engine_in("mission")
    eng.state.operator_state = OperatorState.INCAPACITATED
    eng._auto_safe()
    assert eng.state.mode is Mode.SAFE


def test_auto_safe_comms_denied_degrades(tmp_nous_home: Path) -> None:
    eng = _engine_in("relay")
    eng.state.comms_state = CommsState.DENIED
    eng._auto_safe()
    assert eng.state.mode is Mode.DEGRADED


def test_auto_safe_operator_outranks_device_hazards(tmp_nous_home: Path) -> None:
    # Incapacitated operator plus a critical pack: the operator condition
    # wins and the device takes the full safe posture, not LOW_POWER.
    eng = _engine_in("mission")
    eng.state.operator_state = OperatorState.INCAPACITATED
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.state.mode is Mode.SAFE


@pytest.mark.parametrize("trigger", ["mission", "relay", "monitoring", "c2"])
def test_auto_safe_converges_from_every_operational_mode(
    tmp_nous_home: Path, trigger: str
) -> None:
    # From any operational mode a critical pack moves the FSM out of the
    # operational set in one step, and a second evaluation is a no-op: the
    # one-way loop reaches a fixed point.
    eng = _engine_in(trigger)
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert not is_operational(eng.state.mode)
    settled = eng.state.mode
    eng._auto_safe()
    assert eng.state.mode is settled


def test_auto_safe_records_transition_reason(tmp_nous_home: Path, tmp_path: Path) -> None:
    db_engine = init_db(f"sqlite:///{tmp_path / 'state.db'}")
    log = StateTransitionLog(db_engine)
    eng = Engine(transition_log=log)
    eng.start()
    eng.request_transition("ready")
    eng.request_transition("mission", context=_OK_ENTRY)
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    rows = log.tail(10)
    safe_row = next(
        (r for r in rows if r.trigger == "low_power" and "auto-safe" in r.reason),
        None,
    )
    assert safe_row is not None
    assert safe_row.to_mode == Mode.LOW_POWER.value
