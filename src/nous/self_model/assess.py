"""Self-model assessment: aggregate estimator state into capability claims.

The self-model layer answers the controller's question of the form
"what can the device do right now, and how confident are you?". It
reads the engine's live estimator state -- power, thermal, compute,
comms, biometrics -- and produces calibrated capability claims with
explicit ``p5 / p50 / p95`` quantiles.

The quantile mapping is calibrated via Monte Carlo (BL-035): draw
samples from each estimator's posterior, push them through the
capability function (which is non-linear in places -- endurance
divides by net load, headroom subtracts from the throttle threshold),
then take empirical quantiles. The number of samples
(``_MONTE_CARLO_SAMPLES``) is small enough to stay well under the
per-tick budget but large enough to be stable around 5 / 95 percentiles
for the shapes the simulator produces. The legacy Gaussian
approximation is retained as a fallback when ``mode="gaussian"`` so a
test that needs the v0.1 contract can still opt out.

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
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

import numpy as np
from pydantic import BaseModel, Field

from ..types import Capability

if TYPE_CHECKING:
    from ..engine import Engine

__all__ = ["Assessment", "assess"]


_Z_90 = 1.645
_ENDURANCE_NET_CHARGE_CAP_MIN = 24 * 60.0
_MONTE_CARLO_SAMPLES = 512
_DEFAULT_SEED = 0
_PERCEPTION_RANGE_MAX_M = 60000.0
_PERCEPTION_CONFIDENCE_SCALE_M = 4000.0

QuantileMode = Literal["monte_carlo", "gaussian"]


class Assessment(BaseModel):
    """Aggregated capability claims for a controller-facing answer."""

    question: str
    endurance: Capability | None = None
    thermal_headroom: Capability | None = None
    inference_capacity: Capability | None = None
    perception_range: Capability | None = None
    extra: list[Capability] = Field(default_factory=list)


def assess(
    question: str,
    engine: Engine | None = None,
    *,
    mode: QuantileMode = "monte_carlo",
    seed: int = _DEFAULT_SEED,
) -> Assessment:
    """Return an assessment of the device's current capabilities.

    Reads the engine's live estimator state and returns calibrated
    capability claims. Returns a zero-filled assessment when ``engine``
    is omitted; the legacy stub call site keeps working while the
    server (BL-018) starts passing the engine through.

    ``mode='monte_carlo'`` (default) samples each estimator's posterior
    and takes empirical quantiles -- honest under the non-linearities
    in the endurance and headroom functions. ``mode='gaussian'`` keeps
    the v0.1 linear-Gaussian approximation as an opt-out.
    """
    if engine is None:
        return _empty_assessment(question)

    rng = np.random.default_rng(int(seed))
    endurance = _endurance_capability(engine, mode=mode, rng=rng)
    thermal_headroom = _thermal_headroom_capability(engine, mode=mode, rng=rng)
    inference_capacity = _inference_capacity_capability(engine, mode=mode, rng=rng)
    perception_range = _perception_range_capability(engine, mode=mode, rng=rng)

    return Assessment(
        question=question or "default",
        endurance=endurance,
        thermal_headroom=thermal_headroom,
        inference_capacity=inference_capacity,
        perception_range=perception_range,
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
        perception_range=Capability(
            name="perception_range_m", point=0.0, p5=0.0, p50=0.0, p95=0.0, units="m"
        ),
    )


def _endurance_capability(
    engine: Engine, *, mode: QuantileMode, rng: np.random.Generator
) -> Capability:
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
    battery_wh = float(power.profile.get("power", {}).get("battery_wh", 0.0))

    point_min = _endurance_min(battery_wh, point_soc, net_w)

    if mode == "monte_carlo" and soc_sigma > 0.0 and net_w > 0.0:
        soc_samples = np.clip(
            rng.normal(point_soc, soc_sigma, size=_MONTE_CARLO_SAMPLES),
            0.0,
            100.0,
        )
        endurance_samples = (battery_wh * soc_samples / 100.0) / net_w * 60.0
        p5, p50, p95 = _quantiles(endurance_samples)
    else:
        soc_p5 = max(0.0, point_soc - _Z_90 * soc_sigma)
        soc_p95 = min(100.0, point_soc + _Z_90 * soc_sigma)
        p5 = _endurance_min(battery_wh, soc_p5, net_w)
        p95 = _endurance_min(battery_wh, soc_p95, net_w)
        p50 = point_min

    if net_w <= 0.0:
        confidence = 0.0
        drivers = ["power", "apu"]
    else:
        confidence = max(0.0, 1.0 - soc_sigma / 50.0)
        drivers = ["power"]

    return Capability(
        name="endurance_min",
        point=point_min,
        p5=min(p5, point_min),
        p50=p50,
        p95=max(p95, point_min),
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


def _thermal_headroom_capability(
    engine: Engine, *, mode: QuantileMode, rng: np.random.Generator
) -> Capability:
    """Degrees Celsius headroom to the junction throttle threshold."""
    thermal = engine.thermal
    estimate = engine.thermal_est.state()

    junction_point = float(estimate.point.get("junction_c", thermal.junction_c))
    junction_var = float(estimate.covariance.get("junction_c", 0.0))
    junction_sigma = math.sqrt(max(0.0, junction_var))

    throttle_c = thermal.junction_temp_throttle
    point_c = throttle_c - junction_point

    if mode == "monte_carlo" and junction_sigma > 0.0:
        junction_samples = rng.normal(
            junction_point, junction_sigma, size=_MONTE_CARLO_SAMPLES
        )
        headroom_samples = throttle_c - junction_samples
        p5, p50, p95 = _quantiles(headroom_samples)
    else:
        p5 = throttle_c - (junction_point + _Z_90 * junction_sigma)
        p95 = throttle_c - (junction_point - _Z_90 * junction_sigma)
        p50 = point_c

    confidence = max(0.0, 1.0 - junction_sigma / 10.0)

    return Capability(
        name="thermal_headroom_c",
        point=point_c,
        p5=min(p5, point_c),
        p50=p50,
        p95=max(p95, point_c),
        confidence=confidence,
        drivers=["thermal", "compute"],
        units="C",
    )


def _inference_capacity_capability(
    engine: Engine, *, mode: QuantileMode, rng: np.random.Generator
) -> Capability:
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

    if mode == "monte_carlo" and load_sigma > 0.0:
        load_samples = np.clip(
            rng.normal(load_point, load_sigma, size=_MONTE_CARLO_SAMPLES), 0.0, 100.0
        )
        headroom_samples = (100.0 - load_samples) / 100.0
        capacity_samples = capacity * headroom_samples
        p5, p50, p95 = _quantiles(capacity_samples)
    else:
        headroom_p5 = max(0.0, 100.0 - (load_point + _Z_90 * load_sigma)) / 100.0
        headroom_p95 = max(0.0, 100.0 - (load_point - _Z_90 * load_sigma)) / 100.0
        p5 = capacity * headroom_p5
        p95 = capacity * headroom_p95
        p50 = point

    confidence = 1.0 if not compute.throttled else 0.5

    return Capability(
        name="inference_capacity_tok_per_s",
        point=point,
        p5=min(p5, point),
        p50=p50,
        p95=max(p95, point),
        confidence=confidence,
        drivers=["compute", "thermal"],
        units="tok/s",
    )


def _perception_range_capability(
    engine: Engine, *, mode: QuantileMode, rng: np.random.Generator
) -> Capability:
    """Best-band EO/IR detection range -- the device's perception reach.

    The headline is ``max(eo_range, ir_range)``: the electro-optical band wins by
    day, the infrared band by night or through smoke, so the better of the two is
    the honest answer to "how far can I perceive right now". The Monte Carlo branch
    samples both bands from the EO/IR Kalman posterior and takes the per-sample
    maximum, so the band reflects the nonlinear best-of-two rather than one channel.
    """
    estimate = engine.eoir_est.state()

    eo_point = float(estimate.point.get("eo_range_m", engine.eoir.eo_range_m))
    eo_sigma = math.sqrt(max(0.0, float(estimate.covariance.get("eo_range_m", 0.0))))
    ir_point = float(estimate.point.get("ir_range_m", engine.eoir.ir_range_m))
    ir_sigma = math.sqrt(max(0.0, float(estimate.covariance.get("ir_range_m", 0.0))))

    point = max(eo_point, ir_point)
    dom_sigma = eo_sigma if eo_point >= ir_point else ir_sigma

    if mode == "monte_carlo" and (eo_sigma > 0.0 or ir_sigma > 0.0):
        eo_s = np.clip(
            rng.normal(eo_point, eo_sigma, size=_MONTE_CARLO_SAMPLES),
            0.0,
            _PERCEPTION_RANGE_MAX_M,
        )
        ir_s = np.clip(
            rng.normal(ir_point, ir_sigma, size=_MONTE_CARLO_SAMPLES),
            0.0,
            _PERCEPTION_RANGE_MAX_M,
        )
        p5, p50, p95 = _quantiles(np.maximum(eo_s, ir_s))
    else:
        p5 = max(0.0, point - _Z_90 * dom_sigma)
        p95 = min(_PERCEPTION_RANGE_MAX_M, point + _Z_90 * dom_sigma)
        p50 = point

    confidence = max(0.0, 1.0 - dom_sigma / _PERCEPTION_CONFIDENCE_SCALE_M)

    return Capability(
        name="perception_range_m",
        point=point,
        p5=min(p5, point),
        p50=p50,
        p95=max(p95, point),
        confidence=confidence,
        drivers=["eoir", "sensors"],
        units="m",
    )


def _quantiles(values: np.ndarray) -> tuple[float, float, float]:
    """Empirical 5 / 50 / 95 quantiles of a Monte Carlo sample.

    Each capability's Monte Carlo branch publishes the p50 as the sample
    median (this ``q[1]``), so the band centre and the tails come from the
    same sample rather than mixing a sampled band with a deterministic
    point (audit ASSESS-1). The Gaussian fallback, whose median equals its
    mean, keeps reporting the deterministic point as p50.
    """
    q = np.quantile(values, [0.05, 0.5, 0.95])
    return float(q[0]), float(q[1]), float(q[2])


_QuantilesFn = Callable[[np.random.Generator, int], np.ndarray]
