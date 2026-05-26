"""Self-model explanation: render an :class:`Assessment` for the controller.

The explanation is short and structured: a header line for the
question, one line per capability with its point and confidence
band, plus a short trailer naming the subsystem most responsible for
limiting the answer. The trailer is the half a controller usually
acts on; surfacing it removes a guessing step when the same number
has multiple plausible drivers.
"""

from __future__ import annotations

from ..types import Capability
from .assess import Assessment

__all__ = ["explain"]


def explain(assessment: Assessment) -> str:
    """Return a human-readable explanation of the assessment.

    The output lists each capability's point + p5/p95 envelope and
    closes with a "limiting driver" line that names the subsystem
    contributing the tightest p5 band relative to its point. The
    controller uses this to branch on what to recover first.
    """
    parts: list[str] = [f"question: {assessment.question}"]
    capabilities = [
        cap
        for cap in (
            assessment.endurance,
            assessment.thermal_headroom,
            assessment.inference_capacity,
            *assessment.extra,
        )
        if cap is not None
    ]
    for cap in capabilities:
        parts.append(
            f"{cap.name}: p50={cap.p50:.2f} {cap.units} "
            f"(p5={cap.p5:.2f}, p95={cap.p95:.2f}, "
            f"confidence={cap.confidence:.2f})"
        )
    limiting = _limiting_driver(capabilities)
    if limiting:
        parts.append(f"limiting: {limiting}")
    return "\n".join(parts)


def _limiting_driver(capabilities: list[Capability]) -> str:
    """Pick the capability whose lower band squeezes hardest against its point.

    A small (point - p5) absolute gap and a low ``confidence`` together
    indicate the subsystem the controller should investigate first. We
    rank by ``(1 - confidence) * relative_p5_gap``. Capabilities with
    no drivers or a zero point are skipped (no useful guidance).
    """
    best_score = -1.0
    best: Capability | None = None
    for cap in capabilities:
        if not cap.drivers:
            continue
        denom = abs(cap.point) if cap.point != 0.0 else 1.0
        gap = max(0.0, cap.point - cap.p5) / denom
        score = (1.0 - cap.confidence) * gap
        if score > best_score:
            best_score = score
            best = cap
    if best is None:
        return ""
    return f"{best.name} <- {', '.join(best.drivers)}"
