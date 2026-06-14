"""Declarative mode-requirements gate (ADR 0043).

Entry into an operational mode now gates on the same flag set the auto-safe
watches on the way out: thermal headroom and power reserve (SC-2 / SC-8, the
pre-existing gates), plus an available operator for all four operational modes
and a live comms link for the link-bearing modes (RELAY, C2). These tests pin
the new operator and comms requirements at the bare FSM and through the engine,
and confirm entry and exit read one shared constraint id per condition.
"""

from __future__ import annotations

import pytest

from nous.engine import Engine
from nous.state.comms_state import CommsState
from nous.state.machine import (
    REQ_COMMS_LINK,
    REQ_OPERATOR,
    GuardDenied,
    Mode,
    StateMachine,
    build_fsm_enforcer,
)
from nous.state.operator_state import OperatorState

_OPERATIONAL = ["mission", "relay", "monitoring", "c2"]
_LINK_MODES = ["relay", "c2"]
_NON_LINK_MODES = ["mission", "monitoring"]

_OK_CTX: dict[str, object] = {
    "thermal_headroom_c": 20.0,
    "thermal_headroom_threshold_c": 5.0,
    "soc_pct": 50.0,
    "soc_pct_critical": 5.0,
    "operator_state": "nominal",
    "comms_state": "connected",
}


def _ctx(**overrides: object) -> dict[str, object]:
    return {**_OK_CTX, **overrides}


def _idle() -> StateMachine:
    sm = StateMachine()
    sm.transition("boot")
    sm.transition("ready")
    return sm


# --- bare FSM ----------------------------------------------------------------


@pytest.mark.parametrize("trigger", _OPERATIONAL)
def test_incapacitated_operator_refuses_every_operational_entry(trigger: str) -> None:
    sm = _idle()
    with pytest.raises(GuardDenied) as exc:
        sm.transition(trigger, context=_ctx(operator_state="incapacitated"))
    assert "operator" in str(exc.value).lower()
    assert sm.current is Mode.IDLE


@pytest.mark.parametrize("trigger", _LINK_MODES)
def test_denied_comms_refuses_link_modes(trigger: str) -> None:
    sm = _idle()
    with pytest.raises(GuardDenied) as exc:
        sm.transition(trigger, context=_ctx(comms_state="denied"))
    assert "comms" in str(exc.value).lower()
    assert sm.current is Mode.IDLE


@pytest.mark.parametrize("trigger", _NON_LINK_MODES)
def test_denied_comms_does_not_block_non_link_modes(trigger: str) -> None:
    # A MISSION or MONITORING run does not need a link, so a denied link must
    # not refuse it: the comms requirement is scoped to the link modes only.
    sm = _idle()
    target = sm.transition(trigger, context=_ctx(comms_state="denied"))
    assert sm.current is target
    assert target is not Mode.IDLE


@pytest.mark.parametrize("trigger", _OPERATIONAL)
def test_full_requirements_admit_every_operational_entry(trigger: str) -> None:
    sm = _idle()
    target = sm.transition(trigger, context=_OK_CTX)
    assert sm.current is target
    assert target is not Mode.IDLE


def test_entry_and_exit_share_one_constraint_id() -> None:
    # The entry gate refuses through the same enforcer id the auto-safe records,
    # so one counter aggregates both directions of the operator condition.
    enforcer = build_fsm_enforcer()
    sm = StateMachine(checker=enforcer)
    sm.transition("boot")
    sm.transition("ready")
    with pytest.raises(GuardDenied):
        sm.transition("mission", context=_ctx(operator_state="incapacitated"))
    assert enforcer.violation_count(REQ_OPERATOR) == 1
    assert REQ_OPERATOR == "label:operator-incapacitated"
    assert REQ_COMMS_LINK == "label:comms-denied"


def test_device_hazards_are_named_before_operator() -> None:
    # Gate order keeps the established SC-2 / SC-8 messages surfacing first when
    # several requirements fail at once.
    sm = _idle()
    with pytest.raises(GuardDenied) as exc:
        sm.transition(
            "mission",
            context=_ctx(thermal_headroom_c=1.0, operator_state="incapacitated"),
        )
    assert "SC-2" in str(exc.value)


# --- through the engine ------------------------------------------------------


def test_engine_refuses_relay_into_denied_comms() -> None:
    eng = Engine()
    eng.start()
    assert eng.fsm.current is Mode.IDLE
    eng.state.comms_state = CommsState.DENIED

    ok, mode, reason = eng.request_transition("relay")
    assert not ok
    assert mode is Mode.IDLE
    assert "comms" in reason.lower()

    # MISSION does not require a link, so the same denied state still admits it.
    ok, mode, _ = eng.request_transition("mission")
    assert ok
    assert mode is Mode.MISSION


def test_engine_refuses_operational_entry_when_operator_incapacitated() -> None:
    eng = Engine()
    eng.start()
    eng.state.operator_state = OperatorState.INCAPACITATED

    ok, mode, reason = eng.request_transition("mission")
    assert not ok
    assert mode is Mode.IDLE
    assert "operator" in reason.lower()
