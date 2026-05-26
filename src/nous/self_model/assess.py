"""Self-model assessment: aggregate estimator state into capability claims.

The self-model layer answers the controller's question of the form
"what can the device do right now, and how confident are you?". It
reads the engine's live estimator state -- power, thermal, compute,
comms, biometrics -- and produces calibrated capability claims with
explicit ``p5 / p50 / p95`` quantiles.

The quantiles are derived from each estimator's posterior covariance
(``sigma = sqrt(variance)``) under a Gaussian approximation
(``p5 ~ point - 1.645 * sigma``, ``p95 ~ point + 1.645 * sigma``).
This is a deliberate v0.1 calibration: BL-035 will replace the
Gaussian approximation with the model card's calibrated quantile
mapping. For now, the structure is real (drivers list, units, point
estimate, confidence band) so a controller can already branch on it.

Capabilities surfaced:

* ``endurance_min`` -- minutes the battery can sustain the current net
  load (charge - load). Driven by ``power`` (SoC + net draw).
* ``thermal_headroom_c`` -- degrees of junction headroom before throttle.
  Driven by ``thermal``.
* ``inference_capacity_tok_per_s`` -- token-per-second the compute
  subsystem can sustain right now (after thermal clipping). Driven by
  ``compute`` (load_pct + thermal throttle).

The function takes an :class:`~nous.engine.Engine` so the caller does
not have to thread every estimator through manually; passing
``engine=None`` returns an empty assessment for backward compatibility
with the v0.1 stub call site.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..types import Capability

if TYPE_CHECKING:
    from ..engine import Engine

__all__ = ["Assessment", "assess"]


_Z_90 = 1.645
_ENDURANCE_NET_CHARGE_CAP_MIN = 24 * 60.0


class Assessment(BaseModel):
    """Aggregated capability claims for a controller-facing answer."""

    question: str
    endurance: Capability | None = None
    thermal_headroom: Capability | None = None
    inference_capacity: Capability | None = None
    extra: list[Capability] = Field(default_factory=list)


def assess(question: str, engine: Engine | None = None) -> Assessment:
    """Return an assessment of the device's current capabilities.

    Reads the engine's live estimator state and returns calibrated
    capability claims. Returns a zero-filled assessment when ``engine``
    is omitted; the legacy stub call site keeps working while the
    server (BL-018) starts passing the engine through.
    """
    if engine is None:
        return _empty_assessment(question)

    endurance = _endurance_capability(engine)
    thermal_headroom = _thermal_headroom_capability(engine)
    inference_capacity = _inference_capacity_capability(engine)

    return Assessment(
        question=question or "default",
        endurance=endurance,
        thermal_headroom=thermal_headroom,
        inference_capacity=inference_capacity,
    )


def _empty_assessment(question: str) -> Assessment:
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


def _endurance_capability(engine: Engine) -> Capability:
    """Endurance minutes from SoC, net load, and the SoC posterior.

    Net load is ``load_w - charge_accepted_w``. When the battery is
    being net-charged the endurance is unbounded; we return the
    profile's nominal capacity-derived headroom as ``p50`` and report
    ``confidence=0`` so the controller does not treat it as a hard
    bound.
    """
    power = engine.power
    estimate = engine.power_est.state()

    point_soc = float(estimate.point.get("soc_pct", power.soc_pct))
    soc_var = float(estimate.covariance.get("soc_pct", 0.0))
    soc_sigma = math.sqrt(max(0.0, soc_var))

    net_w = float(power.truth().get("load_w", 0.0)) - float(
        power.truth().get("charge_accepted_w", 0.0)
    )

    soc_p5 = max(0.0, point_soc - _Z_90 * soc_sigma)
    soc_p95 = min(100.0, point_soc + _Z_90 * soc_sigma)

    battery_wh = float(power.profile.get("power", {}).get("battery_wh", 0.0))

    point_min = _endurance_min(battery_wh, point_soc, net_w)
    p5_min = _endurance_min(battery_wh, soc_p5, net_w)
    p95_min = _endurance_min(battery_wh, soc_p95, net_w)

    if net_w <= 0.0:
        confidence = 0.0
        drivers = ["power", "apu"]
    else:
        confidence = max(0.0, 1.0 - soc_sigma / 50.0)
        drivers = ["power"]

    return Capability(
        name="endurance_min",
        point=point_min,
        p5=p5_min,
        p50=point_min,
        p95=p95_min,
        confidence=confidence,
        drivers=drivers,
        units="min",
    )


def _endurance_min(battery_wh: float, soc_pct: float, net_w: float) -> float:
    """Return endurance in minutes.

    When ``net_w <= 0`` the battery is being net-charged and the
    endurance is unbounded; we return a 24h cap (``_ENDURANCE_NET_CHARGE_CAP_MIN``)
    as a JSON-safe sentinel for "more than a day's worth of headroom".
    The caller is expected to read ``confidence=0`` for the
    net-charging branch and treat the figure as a hint rather than a
    hard bound.
    """
    if net_w <= 0.0:
        return _ENDURANCE_NET_CHARGE_CAP_MIN
    remaining_wh = battery_wh * (max(0.0, soc_pct) / 100.0)
    return (remaining_wh / net_w) * 60.0


def _thermal_headroom_capability(engine: Engine) -> Capability:
    """Degrees Celsius headroom to the junction throttle threshold."""
    thermal = engine.thermal
    estimate = engine.thermal_est.state()

    junction_point = float(estimate.point.get("junction_c", thermal.junction_c))
    junction_var = float(estimate.covariance.get("junction_c", 0.0))
    junction_sigma = math.sqrt(max(0.0, junction_var))

    throttle_c = thermal.junction_temp_throttle
    point_c = throttle_c - junction_point
    p5_c = throttle_c - (junction_point + _Z_90 * junction_sigma)
    p95_c = throttle_c - (junction_point - _Z_90 * junction_sigma)

    confidence = max(0.0, 1.0 - junction_sigma / 10.0)

    return Capability(
        name="thermal_headroom_c",
        point=point_c,
        p5=p5_c,
        p50=point_c,
        p95=p95_c,
        confidence=confidence,
        drivers=["thermal", "compute"],
        units="C",
    )


def _inference_capacity_capability(engine: Engine) -> Capability:
    """Tokens-per-second the compute subsystem can sustain right now.

    The headline figure is the profile's
    ``compute.inference_local.tok_per_s_p50`` derated by the fraction
    of compute headroom still available after thermal throttling.
    Quantiles come from the compute Kalman's load-pct posterior.
    """
    compute = engine.compute
    estimate = engine.compute_est.state()

    capacity = compute.tok_per_s_capacity
    if capacity <= 0.0:
        return Capability(
            name="inference_capacity_tok_per_s",
            point=0.0,
            p5=0.0,
            p50=0.0,
            p95=0.0,
            confidence=0.0,
            drivers=["compute", "thermal"],
            units="tok/s",
        )

    load_point = float(estimate.point.get("load_pct", compute.load_pct))
    load_var = float(estimate.covariance.get("load_pct", 0.0))
    load_sigma = math.sqrt(max(0.0, load_var))

    headroom = max(0.0, 100.0 - load_point) / 100.0
    point = capacity * headroom

    headroom_p5 = max(0.0, 100.0 - (load_point + _Z_90 * load_sigma)) / 100.0
    headroom_p95 = max(0.0, 100.0 - (load_point - _Z_90 * load_sigma)) / 100.0

    confidence = 1.0 if not compute.throttled else 0.5

    return Capability(
        name="inference_capacity_tok_per_s",
        point=point,
        p5=capacity * headroom_p5,
        p50=point,
        p95=capacity * headroom_p95,
        confidence=confidence,
        drivers=["compute", "thermal"],
        units="tok/s",
    )
