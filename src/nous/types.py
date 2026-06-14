"""Shared types used across subsystems, estimators, and the self-model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "Capability",
    "Estimate",
    "EstimatorHealth",
    "LinkEstimate",
    "Observation",
    "TickContext",
]


class Observation(BaseModel):
    """A noisy sensor reading emitted by a subsystem.

    The ``source`` identifies the subsystem (``power``, ``thermal``, ...);
    ``payload`` is the structured measurement, ``noise`` describes the
    sensor's calibrated noise model (typically a covariance matrix or
    standard-deviation vector serialised to JSON-safe types).
    """

    source: str
    ts_s: float
    payload: dict[str, Any] = Field(default_factory=dict)
    noise: dict[str, Any] = Field(default_factory=dict)


class EstimatorHealth(BaseModel):
    """What a recursive filter knows about its own fitness.

    These are the diagnostics a real EKF publishes alongside its state (PX4
    exposes the same shape in ``estimator_status``): whether the filter is
    fusing or coasting, how statistically consistent its measurements are,
    and how many it has rejected or reset on. They let a controller tell a
    degraded filter from a merely uncertain one, a distinction the bare
    ``point`` / ``covariance`` pair cannot express.

    ``test_ratio`` is the normalised innovation squared per channel: a value
    above 1 means the last measurement fell outside the gate and was
    rejected. ``test_ratio_filtered`` is its exponentially-weighted, signed
    running value, so a persistently biased sensor shows up (and its
    direction is legible) before it ever trips the gate.
    """

    healthy: bool = True
    fused: bool = True
    dead_reckoning: bool = False
    rejected_updates: int = 0
    reset_count: int = 0
    test_ratio: dict[str, float] = Field(default_factory=dict)
    test_ratio_filtered: dict[str, float] = Field(default_factory=dict)
    innovation: dict[str, float] = Field(default_factory=dict)


class Estimate(BaseModel):
    """A filtered belief about a subsystem state.

    ``point`` is the mean estimate; ``covariance`` is the filter's
    estimated covariance (serialised to a JSON-safe structure);
    ``source`` identifies the estimator that produced it. ``health`` carries
    the filter's innovation-consistency and fault diagnostics when the
    estimator reports them (``None`` for a legacy estimator that does not).
    """

    source: str
    ts_s: float
    point: dict[str, float] = Field(default_factory=dict)
    covariance: dict[str, Any] = Field(default_factory=dict)
    health: EstimatorHealth | None = None


class Capability(BaseModel):
    """A self-model claim about a capability.

    The fields ``p5``/``p50``/``p95`` are calibrated quantiles around the
    point estimate. ``drivers`` lists the subsystems whose state most
    influences the claim.
    """

    name: str
    point: float
    p5: float
    p50: float
    p95: float
    confidence: float = 0.0
    drivers: list[str] = Field(default_factory=list)
    units: str = ""


class LinkEstimate(BaseModel):
    """Comms-link belief produced by the comms estimator."""

    link_id: str
    connected: bool
    rssi_dbm: float
    loss_pct: float
    throughput_bps: float
    bandwidth_bps: float = 0.0
    capacity_bps: float = 0.0


class TickContext(BaseModel):
    """Per-tick metadata threaded through subsystems and estimators."""

    tick: int
    ts_s: float
    dt_s: float
    mode: str
    profile: str
    extra: Mapping[str, Any] = Field(default_factory=dict)
