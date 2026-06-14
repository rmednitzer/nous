"""Runtime safety enforcer (ADR 0022).

The package exposes the structured-result seam that turns an STPA safety
constraint into an observable runtime artefact. See :mod:`nous.safety.enforcer`.
"""

from __future__ import annotations

from .enforcer import (
    CLAMPED,
    ERRORED,
    REFUSED,
    UNREGISTERED,
    Evaluator,
    SafetyEnforcer,
    SafetyResult,
    ceiling_clamp,
    floor_threshold,
    forbid_value,
)

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
