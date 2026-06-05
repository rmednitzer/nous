"""FSM reachability and structural invariants (ADR 0028).

The hand-rolled transition table is small and finite, so these checks are
exhaustive walks rather than sampled properties. They pin the safety
structure the reachability work guarantees: every mode is reachable, a
fail-safe (`SAFE`) and a clean stop (`SHUTDOWN`) are reachable from every
operating or impaired mode, every entry into an operational mode is gated,
and the classification buckets stay disjoint. A regression that strands a
mode or lands an unguarded path into an operational mode fails here.
"""

from __future__ import annotations

from nous.state.machine import (
    _IMPAIRED_MODES,
    _OPERATIONAL_MODES,
    _SAFETY_GATES,
    _TERMINAL_MODES,
    _TRANSITIONS,
    Mode,
    is_impaired,
    is_operational,
    is_terminal,
)


def _reachable_from(start: Mode) -> set[Mode]:
    """Breadth-first closure of modes reachable from ``start`` over the table."""
    seen = {start}
    queue = [start]
    while queue:
        current = queue.pop()
        for (frm, _trigger), to in _TRANSITIONS.items():
            if frm == current and to not in seen:
                seen.add(to)
                queue.append(to)
    return seen


def test_every_mode_is_reachable_from_stowed() -> None:
    assert _reachable_from(Mode.STOWED) == set(Mode)


def test_safe_reachable_in_one_trigger_from_operating_or_impaired() -> None:
    # The fail-safe guarantee: anywhere the device is actually doing work or
    # already impaired, a single `safe` trigger reaches SAFE.
    for mode in _OPERATIONAL_MODES | _IMPAIRED_MODES:
        assert (mode, "safe") in _TRANSITIONS
        assert _TRANSITIONS[(mode, "safe")] is Mode.SAFE


def test_shutdown_reachable_from_every_operating_or_impaired_mode() -> None:
    for mode in _OPERATIONAL_MODES | _IMPAIRED_MODES | {Mode.SAFE}:
        assert Mode.SAFE in _reachable_from(mode) or mode is Mode.SAFE
        assert Mode.SHUTDOWN in _reachable_from(mode)


def test_fault_reachable_from_every_operational_mode() -> None:
    for mode in _OPERATIONAL_MODES:
        assert (mode, "fault") in _TRANSITIONS
        assert _TRANSITIONS[(mode, "fault")] is Mode.FAULT


def test_every_entry_into_an_operational_mode_is_gated() -> None:
    # No transition may land in an operational mode without a safety gate;
    # that is the contract SC-2/SC-8 enforce (ADR 0018, ADR 0022).
    for (frm, trigger), to in _TRANSITIONS.items():
        if is_operational(to):
            assert (frm, trigger) in _SAFETY_GATES, (
                f"unguarded entry into {to.value} via {frm.value} -{trigger}->"
            )


def test_terminal_modes_only_leave_via_reset() -> None:
    for mode in _TERMINAL_MODES:
        triggers = {trig for (frm, trig) in _TRANSITIONS if frm == mode}
        assert triggers == {"reset"}


def test_classification_buckets_are_disjoint() -> None:
    assert not (_OPERATIONAL_MODES & _IMPAIRED_MODES)
    assert not (_OPERATIONAL_MODES & _TERMINAL_MODES)
    assert not (_IMPAIRED_MODES & _TERMINAL_MODES)


def test_classification_helpers_agree_with_buckets() -> None:
    for mode in Mode:
        assert is_operational(mode) is (mode in _OPERATIONAL_MODES)
        assert is_impaired(mode) is (mode in _IMPAIRED_MODES)
        assert is_terminal(mode) is (mode in _TERMINAL_MODES)
    # The holding and transitional states belong to no bucket.
    for mode in (Mode.STOWED, Mode.BOOT, Mode.IDLE, Mode.SAFE):
        assert not (is_operational(mode) or is_impaired(mode) or is_terminal(mode))
