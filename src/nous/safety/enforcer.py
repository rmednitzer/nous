"""Runtime safety enforcer with a structured result (ADR 0022, foundation).

`docs/stpa/05-safety-constraints.md` enumerates the simulator's safety
constraints (SC-1 .. SC-7). ADR 0018 wired SC-2 into the FSM as a transition
guard, but the rest live as prose and guard predicates, not as a runtime
artefact a controller can observe. This module is the seam that closes that
gap: every constraint check returns a :class:`SafetyResult` recording whether
a candidate value was approved, whether it was clamped, and the evidence
behind the verdict. The enforcer keeps a per-constraint and total violation
counter so a controller can read the safe-mode posture at a glance.

Scope of this foundation. The types, the evaluator registry, and the
counters here touch no boundary file, so they ship first as the additive
increment ADR 0022 calls for. The audit-log mirroring under a new
`Tier.SAFETY` classification (which touches `audit.py` and `policy.py`) and
the first real caller (the FSM SC-2 guard, which touches `state/machine.py`)
land in the wiring PR with its own security note. The enforcer ships with no
constraints pre-registered: it governs the seam, not which constraints are
enforced. A call site registers its constraint and then checks against it.

Fail-closed posture. Both shipped evaluators refuse on missing, boolean,
non-numeric, or non-finite context (NaN or infinity) rather than waving the
candidate through. A `check` against an unregistered constraint id, or one
whose evaluator raises, refuses as well, so `check` always returns a
structured disposition and never propagates an exception. A safety check that
cannot establish the evidence it needs denies the action; it never approves
by default.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

__all__ = [
    "CLAMPED",
    "ERRORED",
    "REFUSED",
    "UNREGISTERED",
    "Evaluator",
    "SafetyEnforcer",
    "SafetyResult",
    "ceiling_clamp",
    "floor_threshold",
    "forbid_value",
]

REFUSED = "refused"
CLAMPED = "clamped"
UNREGISTERED = "unregistered"
ERRORED = "errored"


@dataclass(frozen=True)
class SafetyResult:
    """The outcome of one constraint check.

    ``value`` is the value the caller should use: the candidate as a finite
    float when ``approved`` and not clamped, the clamped ceiling when
    ``was_clamped``. A fail-closed refusal echoes the original candidate.
    ``violation_type`` is ``None`` on a clean pass and one of the module
    constants (``REFUSED`` / ``CLAMPED`` / ``UNREGISTERED`` / ``ERRORED``)
    when the constraint fired or its evaluator raised. ``evidence`` carries
    the inputs and a ``detail`` string
    explaining the verdict, suitable for an audit line or a
    ``GuardDenied.reason``.
    """

    approved: bool
    value: Any
    was_clamped: bool = False
    constraint_id: str = ""
    violation_type: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    @property
    def reason(self) -> str:
        """Human-readable disposition, prefixed with the constraint id."""
        detail = self.evidence.get("detail")
        if not detail:
            detail = "approved" if self.approved else "refused"
        return f"{self.constraint_id}: {detail}" if self.constraint_id else str(detail)


Evaluator = Callable[[Any, Mapping[str, Any]], SafetyResult]


def floor_threshold(
    threshold_key: str, *, label: str = "value", unit: str = ""
) -> Evaluator:
    """An evaluator that approves ``candidate >= evidence[threshold_key]``.

    The SC-2 shape: a value must stay at or above a floor (thermal headroom
    at or above its threshold). Refuses fail-closed when either side is
    absent, non-numeric, or non-finite. On any path where coercion succeeded,
    ``SafetyResult.value`` is the candidate as a finite float, so a downstream
    caller never receives a numeric string. The returned
    :class:`SafetyResult` leaves ``constraint_id`` blank;
    :meth:`SafetyEnforcer.check` stamps it.
    """

    def _evaluate(candidate: Any, evidence: Mapping[str, Any]) -> SafetyResult:
        ev = dict(evidence)
        parsed = _coerce_pair(candidate, ev.get(threshold_key))
        if isinstance(parsed, str):
            ev["detail"] = f"{label} {parsed} (fail closed)"
            return SafetyResult(False, candidate, violation_type=REFUSED, evidence=ev)
        value, floor = parsed
        if value < floor:
            ev["detail"] = f"{label} {value:.2f}{unit} below threshold {floor:.2f}{unit}"
            return SafetyResult(False, value, violation_type=REFUSED, evidence=ev)
        return SafetyResult(True, value, evidence=ev)

    return _evaluate


def ceiling_clamp(
    ceiling_key: str, *, label: str = "value", unit: str = ""
) -> Evaluator:
    """An evaluator that clamps ``candidate`` to ``evidence[ceiling_key]``.

    The throttle shape: a value above its ceiling is reduced to the ceiling
    and returned as ``approved`` with ``was_clamped`` set, so the caller uses
    the safe value while the clamp is recorded as a constraint firing.
    Refuses fail-closed when either side is absent, non-numeric, or
    non-finite. On a clean pass ``SafetyResult.value`` is the candidate as a
    finite float, matching the float returned on a clamp.
    """

    def _evaluate(candidate: Any, evidence: Mapping[str, Any]) -> SafetyResult:
        ev = dict(evidence)
        parsed = _coerce_pair(candidate, ev.get(ceiling_key))
        if isinstance(parsed, str):
            ev["detail"] = f"{label} {parsed} (fail closed)"
            return SafetyResult(False, candidate, violation_type=REFUSED, evidence=ev)
        value, cap = parsed
        if value > cap:
            ev["detail"] = f"{label} {value:.2f}{unit} clamped to {cap:.2f}{unit}"
            return SafetyResult(
                True, cap, was_clamped=True, violation_type=CLAMPED, evidence=ev
            )
        return SafetyResult(True, value, evidence=ev)

    return _evaluate


def forbid_value(forbidden: str, *, label: str = "state") -> Evaluator:
    """An evaluator that refuses when the candidate equals ``forbidden``.

    The categorical shape behind the operator and comms mode-entry gates: a
    precondition that a label (the operator state, the comms state) is not in a
    specific unsafe value. Any other value approves; an absent candidate
    refuses fail-closed, so a gate evaluated without its signal denies the
    action rather than waving it through. The candidate is compared as a
    string, so a :class:`~enum.StrEnum` member and its value match the same
    forbidden token.
    """

    def _evaluate(candidate: Any, evidence: Mapping[str, Any]) -> SafetyResult:
        ev = dict(evidence)
        if candidate is None:
            ev["detail"] = f"{label} unknown (fail closed)"
            return SafetyResult(False, candidate, violation_type=REFUSED, evidence=ev)
        current = str(candidate)
        if current == forbidden:
            ev["detail"] = f"{label} is {forbidden}"
            return SafetyResult(False, current, violation_type=REFUSED, evidence=ev)
        return SafetyResult(True, current, evidence=ev)

    return _evaluate


def _coerce_pair(a: Any, b: Any) -> tuple[float, float] | str:
    """Coerce ``(a, b)`` to a finite-float pair, or return a fail-closed reason.

    Returns the parsed floats on success and a short reason string
    (``unknown`` / ``non-numeric`` / ``non-finite``) when either side is
    absent, a boolean, not a number, or not finite (NaN or infinity). Python
    and NumPy booleans are rejected even though ``float(True)`` and
    ``float(np.bool_(False))`` succeed: a boolean in a numeric safety context
    is malformed, not a measurement of 1 or 0, and the simulator's estimator
    paths deal in NumPy scalars. A safety seam treats an infinity as a broken
    estimator, not a valid measurement: an infinite headroom must not approve
    and an infinite ceiling must not wave an unbounded value through.
    """
    if a is None or b is None:
        return "unknown"
    if isinstance(a, bool | np.bool_) or isinstance(b, bool | np.bool_):
        return "non-numeric"
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return "non-numeric"
    if not math.isfinite(fa) or not math.isfinite(fb):
        return "non-finite"
    return (fa, fb)


class SafetyEnforcer:
    """A chokepoint that records every constraint check and its disposition.

    Not thread-safe: the simulator's tick loop is single-threaded, so the
    counters are plain integers. A call site registers its constraint's
    evaluator once, then calls :meth:`check` on the candidate value.
    """

    def __init__(self) -> None:
        self._evaluators: dict[str, Evaluator] = {}
        self._violations: dict[str, int] = {}

    def register(self, constraint_id: str, evaluator: Evaluator) -> None:
        """Bind ``constraint_id`` to the evaluator that judges its candidates."""
        self._evaluators[constraint_id] = evaluator

    def check(
        self,
        constraint_id: str,
        candidate: Any,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> SafetyResult:
        """Judge ``candidate`` against ``constraint_id`` and record the result.

        An unregistered constraint, or one whose evaluator raises, refuses
        fail-closed so ``check`` always returns a structured disposition and
        never propagates an exception to its caller. A refusal or a clamp
        increments the per-id and total violation counters; a clean pass does
        not.
        """
        ev = dict(evidence or {})
        evaluator = self._evaluators.get(constraint_id)
        if evaluator is None:
            ev["detail"] = f"no evaluator registered for {constraint_id} (fail closed)"
            result = SafetyResult(
                False,
                candidate,
                constraint_id=constraint_id,
                violation_type=UNREGISTERED,
                evidence=ev,
            )
        else:
            try:
                result = replace(evaluator(candidate, ev), constraint_id=constraint_id)
            except Exception as exc:  # noqa: BLE001
                message = " ".join(str(exc).split())[:200]
                ev["detail"] = (
                    f"evaluator raised {type(exc).__name__}: {message} (fail closed)"
                )
                result = SafetyResult(
                    False,
                    candidate,
                    constraint_id=constraint_id,
                    violation_type=ERRORED,
                    evidence=ev,
                )
        if not result.approved or result.was_clamped:
            self._violations[constraint_id] = self._violations.get(constraint_id, 0) + 1
        return result

    def violation_count(self, constraint_id: str) -> int:
        """Times ``constraint_id`` has refused or clamped since construction."""
        return self._violations.get(constraint_id, 0)

    @property
    def total_violations(self) -> int:
        return sum(self._violations.values())

    def posture(self) -> dict[str, Any]:
        """A JSON-safe summary for a controller (e.g. via ``device_info``)."""
        return {
            "total_violations": self.total_violations,
            "by_constraint": dict(self._violations),
            "registered": sorted(self._evaluators),
        }
