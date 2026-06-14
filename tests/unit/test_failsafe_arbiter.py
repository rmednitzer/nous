"""Unit tests for the failsafe arbiter framework (ADR 0044).

The arbiter is the reusable half of the tick-loop safing law: it debounces the
raw-active condition set and selects the firing condition by severity. These
tests pin it in isolation, without standing up an engine, the way the ADR
promised the split would allow. They cover severity selection, the debounce
window, the streak cap, and the anti-toggle decay (a flapping condition still
accrues toward firing where a hard reset would hold it off forever).
"""

from __future__ import annotations

import pytest

from nous.state.failsafe import FailsafeArbiter, FailsafeCondition


def _condition(
    cid: str,
    *,
    severity: int = 10,
    debounce_ticks: int = 1,
    decay: int = 1,
    preferred: str = "degrade",
    fallback: str = "degrade",
) -> FailsafeCondition:
    return FailsafeCondition(
        id=cid,
        severity=severity,
        debounce_ticks=debounce_ticks,
        decay=decay,
        preferred=preferred,
        fallback=fallback,
    )


def test_fresh_arbiter_selects_nothing() -> None:
    arbiter = FailsafeArbiter([_condition("a"), _condition("b", severity=20)])
    assert arbiter.select() is None
    assert arbiter.streak("a") == 0


def test_instantaneous_condition_trips_in_one_tick() -> None:
    arbiter = FailsafeArbiter([_condition("a", debounce_ticks=1)])
    arbiter.observe({"a": True})
    assert arbiter.tripped("a")
    selected = arbiter.select()
    assert selected is not None and selected.id == "a"


def test_debounced_condition_requires_the_full_window() -> None:
    arbiter = FailsafeArbiter([_condition("a", debounce_ticks=3)])
    arbiter.observe({"a": True})
    assert not arbiter.tripped("a")
    arbiter.observe({"a": True})
    assert not arbiter.tripped("a")
    arbiter.observe({"a": True})
    assert arbiter.tripped("a")


def test_streak_caps_at_the_debounce_threshold() -> None:
    arbiter = FailsafeArbiter([_condition("a", debounce_ticks=2)])
    for _ in range(5):
        arbiter.observe({"a": True})
    assert arbiter.streak("a") == 2


def test_select_returns_highest_severity_tripped() -> None:
    low = _condition("low", severity=10)
    high = _condition("high", severity=40)
    arbiter = FailsafeArbiter([low, high])
    arbiter.observe({"low": True, "high": True})
    selected = arbiter.select()
    assert selected is not None and selected.id == "high"


def test_select_skips_untripped_higher_severity() -> None:
    # The higher-severity condition needs a longer window; until it trips, the
    # lower-severity instantaneous one is the live failsafe.
    low = _condition("low", severity=10, debounce_ticks=1)
    high = _condition("high", severity=40, debounce_ticks=3)
    arbiter = FailsafeArbiter([low, high])
    arbiter.observe({"low": True, "high": True})
    selected = arbiter.select()
    assert selected is not None and selected.id == "low"


def test_inactive_decays_then_clears_the_streak() -> None:
    arbiter = FailsafeArbiter([_condition("a", debounce_ticks=3, decay=1)])
    arbiter.observe({"a": True})
    arbiter.observe({"a": True})
    assert arbiter.streak("a") == 2
    arbiter.observe({"a": False})
    assert arbiter.streak("a") == 1
    arbiter.observe({"a": False})
    assert arbiter.streak("a") == 0


def test_decay_floors_at_zero() -> None:
    arbiter = FailsafeArbiter([_condition("a", debounce_ticks=3, decay=5)])
    arbiter.observe({"a": True})
    arbiter.observe({"a": False})
    assert arbiter.streak("a") == 0


def test_missing_condition_id_decays_like_inactive() -> None:
    # A raw-active map that omits a condition is read as inactive for it, so an
    # absent key decays the streak rather than raising.
    arbiter = FailsafeArbiter([_condition("a", debounce_ticks=3)])
    arbiter.observe({"a": True})
    arbiter.observe({})
    assert arbiter.streak("a") == 0


def test_anti_toggle_flapping_trips_where_a_hard_reset_would_not() -> None:
    # The property the audit asked for: under a 2-on/1-off/2-on flap, the
    # anti-toggle decay (one per clear tick) lets a sustained-but-noisy fault
    # cross the window, while a hard reset to zero on any clear tick holds it
    # off forever. Same condition, same sequence; only the decay differs.
    sequence = [True, True, False, True, True]
    anti_toggle = FailsafeArbiter([_condition("a", debounce_ticks=3, decay=1)])
    hard_reset = FailsafeArbiter([_condition("a", debounce_ticks=3, decay=3)])
    for active in sequence:
        anti_toggle.observe({"a": active})
        hard_reset.observe({"a": active})
    assert anti_toggle.tripped("a")
    assert not hard_reset.tripped("a")


def test_observe_is_deterministic_for_replay() -> None:
    # Two arbiters fed the identical sequence reach the identical selection, so
    # a scenario replays the same safing decision (ADR 0019).
    conditions = [_condition("a", severity=10, debounce_ticks=2), _condition("b", severity=30)]
    sequence = [{"a": True}, {"a": True, "b": True}, {"a": False, "b": True}]
    first = FailsafeArbiter(conditions)
    second = FailsafeArbiter(conditions)
    for active in sequence:
        first.observe(active)
        second.observe(active)
    a_sel = first.select()
    b_sel = second.select()
    assert a_sel is not None and b_sel is not None
    assert a_sel.id == b_sel.id == "b"


def test_equal_severity_selection_is_order_independent() -> None:
    # Equal severity: the id breaks the tie, so the selection does not depend
    # on the order the conditions were handed to the arbiter (ADR 0019 replay).
    a = _condition("aaa", severity=20)
    b = _condition("bbb", severity=20)
    forward = FailsafeArbiter([a, b])
    reverse = FailsafeArbiter([b, a])
    forward.observe({"aaa": True, "bbb": True})
    reverse.observe({"aaa": True, "bbb": True})
    f_sel = forward.select()
    r_sel = reverse.select()
    assert f_sel is not None and r_sel is not None
    assert f_sel.id == r_sel.id == "aaa"


def test_duplicate_condition_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate failsafe condition id"):
        FailsafeArbiter([_condition("a"), _condition("a", severity=20)])


def test_non_positive_debounce_is_rejected() -> None:
    # A zero debounce would read as permanently tripped; reject at construction.
    with pytest.raises(ValueError, match="debounce_ticks must be >= 1"):
        _condition("a", debounce_ticks=0)


def test_non_positive_decay_is_rejected() -> None:
    # A zero decay would never clear an accrued streak; reject at construction.
    with pytest.raises(ValueError, match="decay must be >= 1"):
        _condition("a", decay=0)
