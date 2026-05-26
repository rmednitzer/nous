"""Self-model viability: decide if a proposed task is feasible right now.

The viability layer turns the controller's request (a free-text task
plus an optional structured ``requirements`` mapping) into a
boolean ``feasible`` plus a short reason. Requirements are matched
against the assessment's capability quantiles -- conservative side
(``p5``) so a marginal capability fails closed.

Recognised requirement keys (all optional):

* ``endurance_min`` -- required minutes of endurance under the
  current net load. Compared against the endurance capability's
  ``p5``.
* ``thermal_headroom_c`` -- required junction headroom in degrees C.
  Compared against the thermal headroom capability's ``p5``.
* ``inference_tok_per_s`` -- required sustained inference rate.
  Compared against the inference capacity capability's ``p5``.

If the controller passes no requirements, the viability layer falls
back to keyword sniffing on the task string -- "run mission for 60
min", "burst inference", "overnight relay" -- so the v0.1 surface is
useful even without structured input.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from .assess import Assessment

__all__ = ["Viability", "viability"]


class Viability(BaseModel):
    feasible: bool
    confidence: float
    reason: str


def viability(
    assessment: Assessment,
    task: str,
    *,
    requirements: Mapping[str, Any] | None = None,
) -> Viability:
    """Return a viability decision for ``task`` against ``assessment``.

    The decision is conservative (uses each capability's ``p5``
    quantile) and short (single string reason). The aggregated
    confidence is the minimum of the capabilities the requirement
    actually touched, so a single uncertain driver lowers the whole
    answer's confidence.
    """
    req = dict(requirements or {})
    if not req:
        req = _infer_requirements(task)

    failures: list[str] = []
    confidences: list[float] = []

    if "endurance_min" in req:
        need = float(req["endurance_min"])
        cap = assessment.endurance
        if cap is None:
            failures.append("endurance capability unavailable; cannot verify")
        else:
            confidences.append(cap.confidence)
            if cap.p5 < need:
                failures.append(
                    f"endurance p5 {cap.p5:.1f} min < required {need:.1f} min"
                )

    if "thermal_headroom_c" in req:
        need = float(req["thermal_headroom_c"])
        cap = assessment.thermal_headroom
        if cap is None:
            failures.append("thermal headroom capability unavailable; cannot verify")
        else:
            confidences.append(cap.confidence)
            if cap.p5 < need:
                failures.append(
                    f"thermal headroom p5 {cap.p5:.1f}C < required {need:.1f}C"
                )

    if "inference_tok_per_s" in req:
        need = float(req["inference_tok_per_s"])
        cap = assessment.inference_capacity
        if cap is None:
            failures.append("inference capacity capability unavailable; cannot verify")
        else:
            confidences.append(cap.confidence)
            if cap.p5 < need:
                failures.append(
                    f"inference p5 {cap.p5:.1f} tok/s < required {need:.1f} tok/s"
                )

    confidence = min(confidences) if confidences else 0.0

    if not failures:
        return Viability(
            feasible=True,
            confidence=confidence,
            reason=(
                f"all requirements met for task {task!r}"
                if req
                else f"no measurable requirements parsed from task {task!r}"
            ),
        )
    return Viability(
        feasible=False,
        confidence=confidence,
        reason="; ".join(failures),
    )


_ENDURANCE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(min|minute|h|hour|hr)", re.I)
_RATE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(tok|tokens?)\s*/?\s*(s|sec|second)?", re.I)


def _infer_requirements(task: str) -> dict[str, float]:
    """Best-effort keyword sniff on the task string.

    A scenario or a quick prompt often phrases requirements
    informally: "run mission for 60 min", "sustain 150 tok/s". We
    pull the obvious numbers out and pass them to the structured
    checker so the controller does not have to spell out a
    requirements dict for the common case.
    """
    out: dict[str, float] = {}
    if not task:
        return out
    text = task.lower()

    match = _ENDURANCE_PATTERN.search(text)
    if match:
        value = float(match.group(1))
        unit = match.group(2)
        if unit.startswith("h"):
            value *= 60.0
        out["endurance_min"] = value

    match = _RATE_PATTERN.search(text)
    if match:
        out["inference_tok_per_s"] = float(match.group(1))

    if any(word in text for word in ("overnight", "all night")):
        out.setdefault("endurance_min", 8 * 60.0)
    if "burst" in text or "high-rate" in text:
        out.setdefault("inference_tok_per_s", 150.0)

    return out
