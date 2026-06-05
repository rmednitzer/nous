"""State machine transition table breadth and contract.

Closes ``AUDIT.md`` H1 for the state-machine half. The existing
``test_state_machine_guards.py`` covers SC-2 (thermal-headroom gate)
and SC-8 (power-reserve gate) plus the unknown-trigger refusal.
This file covers the transition table itself: every documented
transition lands on its declared target, ``can()`` and ``would()``
agree with ``transition()``, history records every successful
transition, refused transitions do not pollute history, and a
Hypothesis property walks arbitrary triggers without diverging from
the table.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nous.state.machine import (
    _TRANSITIONS,
    GuardDenied,
    Mode,
    StateMachine,
)

# Guarded transitions need a passing context so the table breadth test
# is not blocked by SC-2 / SC-8. Real-world callers always pass a
# context with these signals; the gates exist to refuse when the
# context says the device is unsafe, not when it is absent (the
# unknown-context case is covered by ``test_state_machine_guards``).
# Every transition into an operational mode is gated on both thermal
# headroom and power reserve, so each entry supplies both.
_OK_CONTEXT: dict[str, float] = {
    "thermal_headroom_c": 20.0,
    "thermal_headroom_threshold_c": 5.0,
    "soc_pct": 50.0,
    "soc_pct_critical": 5.0,
}
_GUARDED_TRANSITIONS: dict[tuple[Mode, str], dict[str, float]] = {
    (Mode.IDLE, "mission"): _OK_CONTEXT,
    (Mode.IDLE, "relay"): _OK_CONTEXT,
    (Mode.IDLE, "monitoring"): _OK_CONTEXT,
    (Mode.IDLE, "c2"): _OK_CONTEXT,
    (Mode.DEGRADED, "recover"): _OK_CONTEXT,
    (Mode.THERMAL_LIMIT, "cool"): _OK_CONTEXT,
    (Mode.LOW_POWER, "recover"): _OK_CONTEXT,
}


@pytest.mark.parametrize(
    ("frm", "trigger", "to"),
    [(frm, trigger, to) for (frm, trigger), to in _TRANSITIONS.items()],
)
def test_every_table_entry_lands_on_its_documented_target(
    frm: Mode, trigger: str, to: Mode
) -> None:
    fsm = StateMachine(start=frm)
    ctx = _GUARDED_TRANSITIONS.get((frm, trigger), {})
    target = fsm.transition(trigger, context=ctx)
    assert target is to
    assert fsm.current is to


def test_unknown_trigger_raises_value_error() -> None:
    fsm = StateMachine()
    with pytest.raises(ValueError, match="no transition"):
        fsm.transition("there_is_no_such_trigger")


def test_can_agrees_with_transition_admission() -> None:
    fsm = StateMachine()
    assert fsm.can("boot") is True
    assert fsm.can("mission") is False
    fsm.transition("boot")
    assert fsm.can("ready") is True
    assert fsm.can("mission") is False


def test_would_returns_destination_or_none() -> None:
    fsm = StateMachine()
    assert fsm.would("boot") is Mode.BOOT
    assert fsm.would("mission") is None


def test_history_records_every_successful_transition() -> None:
    fsm = StateMachine()
    fsm.transition("boot")
    fsm.transition("ready")
    assert fsm.history() == [
        (Mode.STOWED, "boot", Mode.BOOT),
        (Mode.BOOT, "ready", Mode.IDLE),
    ]


def test_history_excludes_guard_refusals() -> None:
    fsm = StateMachine()
    fsm.transition("boot")
    fsm.transition("ready")
    with pytest.raises(GuardDenied):
        fsm.transition("mission")
    assert fsm.current is Mode.IDLE
    assert fsm.history() == [
        (Mode.STOWED, "boot", Mode.BOOT),
        (Mode.BOOT, "ready", Mode.IDLE),
    ]
    refusals = fsm.refusals()
    assert len(refusals) == 1
    assert refusals[0][1] == "mission"


def test_history_excludes_unknown_trigger_attempts() -> None:
    fsm = StateMachine()
    with pytest.raises(ValueError):
        fsm.transition("bogus")
    assert fsm.history() == []
    assert fsm.refusals() == []


def test_reset_forces_state_without_traversal() -> None:
    fsm = StateMachine()
    fsm.transition("boot")
    fsm.reset(Mode.SHUTDOWN)
    assert fsm.current is Mode.SHUTDOWN
    # The traversed transition stays in history; reset is not a traversal.
    assert fsm.history() == [(Mode.STOWED, "boot", Mode.BOOT)]


@given(trigger=st.text(min_size=1, max_size=30))
def test_transition_is_total_under_arbitrary_trigger(trigger: str) -> None:
    """``transition()`` always either advances or raises ``ValueError``.

    Property invariant: there is no silent no-op branch. A trigger that
    is not in the table from the current mode must raise; a trigger
    that is in the table must advance the machine to the documented
    target. The Hypothesis fuzz exercises arbitrary inputs from the
    STOWED start state.
    """
    fsm = StateMachine()
    key = (Mode.STOWED, trigger)
    if key in _TRANSITIONS:
        ctx = _GUARDED_TRANSITIONS.get(key, {})
        target = fsm.transition(trigger, context=ctx)
        assert target is _TRANSITIONS[key]
    else:
        with pytest.raises(ValueError, match="no transition"):
            fsm.transition(trigger)
