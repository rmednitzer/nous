"""Shared types used across subsystems, estimators, and the self-model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "Capability",
    "Estimate",
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


class Estimate(BaseModel):
    """A filtered belief about a subsystem state.

    ``point`` is the mean estimate; ``covariance`` is the filter's
    estimated covariance (serialised to a JSON-safe structure);
    ``source`` identifies the estimator that produced it.
    """

    source: str
    ts_s: float
    point: dict[str, float] = Field(default_factory=dict)
    covariance: dict[str, Any] = Field(default_factory=dict)


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


class TickContext(BaseModel):
    """Per-tick metadata threaded through subsystems and estimators."""

    tick: int
    ts_s: float
    dt_s: float
    mode: str
    profile: str
    extra: Mapping[str, Any] = Field(default_factory=dict)
