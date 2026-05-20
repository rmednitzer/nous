"""Self-model viability check: is a proposed task feasible right now?"""

from __future__ import annotations

from pydantic import BaseModel

from .assess import Assessment

__all__ = ["Viability", "viability"]


class Viability(BaseModel):
    feasible: bool
    confidence: float
    reason: str


def viability(assessment: Assessment, task: str) -> Viability:
    """Return a placeholder viability decision.

    The L1 implementation compares ``task`` to a small library of profiles
    and consults the assessment's capability quantiles.
    """
    return Viability(
        feasible=True,
        confidence=0.0,
        reason=f"viability rule for task {task!r} lands in L1",
    )
