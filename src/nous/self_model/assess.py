"""Self-model assessment: capability claims with calibrated quantiles."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..types import Capability

__all__ = ["Assessment", "assess"]


class Assessment(BaseModel):
    """Aggregated capability claims for a controller-facing answer."""

    question: str
    endurance: Capability | None = None
    thermal_headroom: Capability | None = None
    inference_capacity: Capability | None = None
    extra: list[Capability] = Field(default_factory=list)


def assess(question: str) -> Assessment:
    """Return a placeholder assessment.

    The real implementation lands in L1 (BL-035). It will read estimator
    output for power, thermal, compute, and comms and produce calibrated
    capability claims via the parametric self-model rules.
    """
    return Assessment(
        question=question or "default",
        endurance=Capability(
            name="endurance_min", point=0.0, p5=0.0, p50=0.0, p95=0.0, units="min"
        ),
        thermal_headroom=Capability(
            name="thermal_headroom_c", point=0.0, p5=0.0, p50=0.0, p95=0.0, units="C"
        ),
        inference_capacity=Capability(
            name="inference_capacity_tok_per_s",
            point=0.0,
            p5=0.0,
            p50=0.0,
            p95=0.0,
            units="tok/s",
        ),
    )
