"""FSM safety-gate tests: SC-2 thermal headroom + SC-8 power reserve.

These tests close the gap identified in the adversarial review (D-01):
``IDLE -> MISSION`` and ``THERMAL_LIMIT -> MISSION`` were table-permitted
without any precondition. Every transition into an operational mode now
routes through the SafetyEnforcer (ADR 0022) and refuses when the thermal
context says headroom is exhausted (SC-2) or the power context says the
battery is below its critical reserve (SC-8).
"""

from __future__ import annotations

import pytest

from nous.state.machine import GuardDenied, Mode, StateMachine

# A context that passes every gate, so a test can flip exactly one signal
# unsafe and know which constraint refused. Beyond thermal and power it carries
# the operator and comms labels the ADR 0043 entry gates read.
_OK: dict[str, object] = {
    "thermal_headroom_c": 20.0,
    "thermal_headroom_threshold_c": 5.0,
    "soc_pct": 50.0,
    "soc_pct_critical": 5.0,
    "operator_state": "nominal",
    "comms_state": "connected",
}


def _ctx(**overrides: object) -> dict[str, object]:
    return {**_OK, **overrides}


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
    target = fsm.transition("mission", context=_ctx(thermal_headroom_c=12.0))
    assert target is Mode.MISSION


def test_thermal_limit_cool_refused_when_still_hot() -> None:
    fsm = StateMachine()
    _boot(fsm)
    fsm.transition("mission", context=_ctx(thermal_headroom_c=10.0))
    fsm.transition("thermal_limit")
    with pytest.raises(GuardDenied) as exc:
        fsm.transition("cool", context=_ctx(thermal_headroom_c=1.0))
    assert "SC-2" in str(exc.value)
    assert fsm.current is Mode.THERMAL_LIMIT


def test_low_power_recover_refused_under_critical_soc() -> None:
    fsm = StateMachine()
    _boot(fsm)
    fsm.transition("mission", context=_ctx(thermal_headroom_c=10.0))
    fsm.transition("low_power")
    # Thermal is healthy here, so SC-8 (power reserve) is the gate that fires.
    with pytest.raises(GuardDenied) as exc:
        fsm.transition("recover", context=_ctx(soc_pct=2.0))
    assert "SC-8" in str(exc.value)
    assert "SoC" in str(exc.value)
    assert fsm.current is Mode.LOW_POWER


@pytest.mark.parametrize("trigger", ["mission", "relay", "monitoring", "c2"])
def test_operational_entry_refused_when_hot(trigger: str) -> None:
    """SC-2 gates every operational-mode entry from IDLE, not just mission."""
    fsm = StateMachine()
    _boot(fsm)
    with pytest.raises(GuardDenied) as exc:
        fsm.transition(trigger, context=_ctx(thermal_headroom_c=1.0))
    assert "SC-2" in str(exc.value)
    assert fsm.current is Mode.IDLE


@pytest.mark.parametrize("trigger", ["mission", "relay", "monitoring", "c2"])
def test_operational_entry_refused_under_critical_soc(trigger: str) -> None:
    """SC-8 gates every operational-mode entry from IDLE on a dying pack."""
    fsm = StateMachine()
    _boot(fsm)
    with pytest.raises(GuardDenied) as exc:
        fsm.transition(trigger, context=_ctx(soc_pct=3.0))
    assert "SC-8" in str(exc.value)
    assert fsm.current is Mode.IDLE


@pytest.mark.parametrize("trigger", ["mission", "relay", "monitoring", "c2"])
def test_operational_entry_admitted_with_headroom_and_reserve(trigger: str) -> None:
    fsm = StateMachine()
    _boot(fsm)
    target = fsm.transition(trigger, context=_OK)
    assert target is not Mode.IDLE
    assert fsm.current is target


def test_last_safety_checks_cleared_after_unknown_trigger() -> None:
    # A gated attempt populates last_safety_checks; a subsequent unknown
    # trigger raises ValueError before the gate loop and must not leave the
    # prior results behind for the engine's audit mirror to read.
    fsm = StateMachine()
    _boot(fsm)
    with pytest.raises(GuardDenied):
        fsm.transition("mission", context=_ctx(thermal_headroom_c=1.0))
    assert fsm.last_safety_checks()
    with pytest.raises(ValueError, match="no transition"):
        fsm.transition("there_is_no_such_trigger")
    assert fsm.last_safety_checks() == []


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
