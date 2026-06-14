"""Failsafe condition framework for the tick-loop auto-safe (ADR 0044).

The engine drives the FSM toward a safer mode when a safety condition trips.
This module holds the reusable half of that law, separated from the engine's
detectors the way PX4 separates its ``FailsafeBase`` framework from the
concrete ``checkStateAndMode``: a declarative :class:`FailsafeCondition` and a
pure :class:`FailsafeArbiter`.

The arbiter is fed the set of raw-active condition ids each tick. It grows each
active condition's debounce streak (capped at the condition's threshold) and
decays each inactive one. The decay is by one per clear tick rather than a
reset to zero, so a sustained but noisy condition still accrues toward firing
(the anti-toggle hysteresis): a single-tick recovery in an otherwise steady
fault no longer hands back the whole grace period. The arbiter then selects the
highest-severity condition whose streak has reached its threshold, leaving the
detection (which needs the engine's live state and the safety enforcer) and the
actuation (firing the trigger) to the caller.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = ["FailsafeArbiter", "FailsafeCondition"]


@dataclass(frozen=True)
class FailsafeCondition:
    """One auto-safing condition: when it trips, and what it does.

    ``severity`` orders the firing when several conditions are tripped at once
    (higher fires first). ``debounce_ticks`` is the streak the condition must
    reach before it trips (one means instantaneous). ``decay`` is how much the
    streak drops per inactive tick: a decay below ``debounce_ticks`` is the
    anti-toggle, holding a sustained-but-flapping condition's progress.
    ``preferred`` is the FSM trigger to drive toward safety; ``fallback`` is the
    trigger to use when the table offers no preferred edge from the current
    mode.
    """

    id: str
    severity: int
    debounce_ticks: int
    decay: int
    preferred: str
    fallback: str


class FailsafeArbiter:
    """Tracks per-condition debounce streaks and selects the firing condition.

    Pure and deterministic: the same sequence of :meth:`observe` calls always
    yields the same selection, so a scenario replays identically (ADR 0019).
    Not thread-safe, like the rest of the single-threaded tick loop.
    """

    def __init__(self, conditions: Sequence[FailsafeCondition]) -> None:
        self._by_id: dict[str, FailsafeCondition] = {c.id: c for c in conditions}
        self._order: tuple[FailsafeCondition, ...] = tuple(
            sorted(conditions, key=lambda c: -c.severity)
        )
        self._streak: dict[str, int] = {c.id: 0 for c in conditions}

    def observe(self, active: Mapping[str, bool]) -> None:
        """Advance every condition's streak from this tick's raw-active set."""
        for cid, cond in self._by_id.items():
            if active.get(cid, False):
                self._streak[cid] = min(cond.debounce_ticks, self._streak[cid] + 1)
            else:
                self._streak[cid] = max(0, self._streak[cid] - cond.decay)

    def tripped(self, condition_id: str) -> bool:
        """True once a condition's streak has reached its debounce threshold."""
        return self._streak[condition_id] >= self._by_id[condition_id].debounce_ticks

    def select(self) -> FailsafeCondition | None:
        """The highest-severity tripped condition, or ``None`` when none is."""
        for cond in self._order:
            if self.tripped(cond.id):
                return cond
        return None

    def streak(self, condition_id: str) -> int:
        """Current debounce streak for ``condition_id`` (for status and tests)."""
        return self._streak[condition_id]
