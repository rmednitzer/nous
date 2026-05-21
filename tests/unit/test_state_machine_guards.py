"""FSM guard tests: SC-2 thermal headroom + SC-5 low-power recovery.

These tests close the gap identified in the adversarial review (D-01):
``IDLE -> MISSION`` and ``THERMAL_LIMIT -> MISSION`` were table-permitted
without any precondition. The FSM now consults a guard for those
transitions and refuses when the thermal context says headroom is
exhausted.
"""

from __future__ import annotations

import pytest

from nous.state.machine import GuardDenied, Mode, StateMachine


def _boot(fsm: StateMachine) -> None:
    fsm.transition("boot")
    fsm.transition("ready")


def test_mission_refused_without_thermal_context() -> None:
    fsm = StateMachine()
    _boot(fsm)
    with pytest.raises(GuardDenied) as exc:
        fsm.transition("mission")
    assert "thermal headroom unknown" in str(exc.value)
    assert fsm.current is Mode.IDLE


def test_mission_refused_when_headroom_below_threshold() -> None:
    fsm = StateMachine()
    _boot(fsm)
    with pytest.raises(GuardDenied) as exc:
        fsm.transition(
            "mission",
            context={"thermal_headroom_c": 1.0, "thermal_headroom_threshold_c": 5.0},
        )
    assert "below threshold" in str(exc.value)
    assert fsm.current is Mode.IDLE


def test_mission_admitted_when_headroom_above_threshold() -> None:
    fsm = StateMachine()
    _boot(fsm)
    target = fsm.transition(
        "mission",
        context={"thermal_headroom_c": 12.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert target is Mode.MISSION


def test_thermal_limit_cool_refused_when_still_hot() -> None:
    fsm = StateMachine()
    _boot(fsm)
    fsm.transition(
        "mission",
        context={"thermal_headroom_c": 10.0, "thermal_headroom_threshold_c": 5.0},
    )
    fsm.transition("thermal_limit")
    with pytest.raises(GuardDenied):
        fsm.transition(
            "cool",
            context={"thermal_headroom_c": 1.0, "thermal_headroom_threshold_c": 5.0},
        )
    assert fsm.current is Mode.THERMAL_LIMIT


def test_low_power_recover_refused_under_critical_soc() -> None:
    fsm = StateMachine()
    _boot(fsm)
    fsm.transition(
        "mission",
        context={"thermal_headroom_c": 10.0, "thermal_headroom_threshold_c": 5.0},
    )
    fsm.transition("low_power")
    with pytest.raises(GuardDenied):
        fsm.transition("recover", context={"soc_pct": 2.0, "soc_pct_critical": 5.0})
    assert fsm.current is Mode.LOW_POWER


def test_guard_refusals_are_recorded() -> None:
    fsm = StateMachine()
    _boot(fsm)
    with pytest.raises(GuardDenied):
        fsm.transition("mission")
    refusals = fsm.refusals()
    assert len(refusals) == 1
    frm, trigger, to, _reason = refusals[0]
    assert frm is Mode.IDLE
    assert trigger == "mission"
    assert to is Mode.MISSION


def test_reset_helper_skips_transition_table() -> None:
    fsm = StateMachine(start=Mode.MISSION)
    fsm.reset(Mode.STOWED)
    assert fsm.current is Mode.STOWED


def test_unknown_trigger_remains_a_hard_error() -> None:
    fsm = StateMachine()
    with pytest.raises(ValueError, match="no transition"):
        fsm.transition("there_is_no_such_trigger")
