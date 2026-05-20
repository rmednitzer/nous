"""Self-model explanation: render an :class:`Assessment` for the controller."""

from __future__ import annotations

from .assess import Assessment

__all__ = ["explain"]


def explain(assessment: Assessment) -> str:
    """Return a human-readable explanation of the assessment.

    The L1 implementation walks the capability drivers and surfaces which
    subsystem most constrains the answer.
    """
    parts: list[str] = [f"question: {assessment.question}"]
    for cap in (
        assessment.endurance,
        assessment.thermal_headroom,
        assessment.inference_capacity,
        *assessment.extra,
    ):
        if cap is None:
            continue
        parts.append(
            f"{cap.name}: p50={cap.p50:.2f} {cap.units} (p5={cap.p5:.2f}, p95={cap.p95:.2f})"
        )
    return "\n".join(parts)
