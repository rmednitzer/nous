"""Internal vocabulary for operator status.

The vocabulary is project-internal (ADR-0006). It is *not* a medical
grading; it is a label the self-model uses to summarise the current
biometric estimate for the controller.
"""

from __future__ import annotations

from enum import StrEnum

from ..types import Estimate

__all__ = ["OperatorState", "derive"]


class OperatorState(StrEnum):
    NOMINAL = "nominal"
    ELEVATED = "elevated"
    STRESSED = "stressed"
    IMPAIRED = "impaired"
    INCAPACITATED = "incapacitated"


def derive(estimate: Estimate) -> tuple[OperatorState, str]:
    """Map a biometric estimate to an :class:`OperatorState` plus rationale.

    The thresholds below are conservative placeholders for v0.1; the
    biometrics model card documents the bounds that will replace them.
    """
    point = estimate.point or {}
    hr = float(point.get("heart_rate_bpm", 70.0))
    core_c = float(point.get("core_temp_c", 37.0))
    cog_load = float(point.get("cognitive_load", 0.2))

    if core_c >= 40.0 or hr >= 200.0:
        return OperatorState.INCAPACITATED, "core temperature or heart rate at incapacitating bound"
    if core_c >= 39.0 or hr >= 175.0 or cog_load >= 0.9:
        return OperatorState.IMPAIRED, "core temperature, heart rate, or cognitive load impaired"
    if core_c >= 38.0 or hr >= 150.0 or cog_load >= 0.7:
        return OperatorState.STRESSED, "biometric signals indicate sustained stress"
    if hr >= 120.0 or cog_load >= 0.5:
        return OperatorState.ELEVATED, "elevated heart rate or cognitive load"
    return OperatorState.NOMINAL, "biometric signals within nominal envelope"
