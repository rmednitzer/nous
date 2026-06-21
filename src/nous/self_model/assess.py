"""Self-model assessment: aggregate estimator state into capability claims.

The self-model layer answers the controller's question of the form
"what can the device do right now, and how confident are you?". It
reads the engine's live estimator state -- power, thermal, compute,
comms, biometrics -- and produces calibrated capability claims with
explicit ``p5 / p50 / p95`` quantiles.

The quantile mapping is calibrated via Monte Carlo (BL-035, ADR 0080):
draw samples from every uncertain input the capability depends on, not
just one, push them through the capability function (which is non-linear
in places -- endurance divides by net load, headroom subtracts from the
throttle threshold), then take empirical quantiles. Each capability draws
from the estimator posteriors that feed it (SoC for endurance, the
junction posterior for headroom, the load posterior for capacity) and,
for the spec constants that have no estimator (``battery_wh``, the
throttle threshold, the benchmark token rate), a small
profile-configurable design prior. Endurance also propagates the
APU-charge and compute-draw posteriors through net load by default
(disable with ``self_model.priors.propagate_net_load: false``); near
energy balance the ``1/net_w`` term is heavy-tailed, so the band stays
wide and its upper tail is capped conservatively at the point estimate
there rather than saturating (ADR 0082). So the bands reflect total
uncertainty rather than understating it behind a single source. The
number of samples (``_MONTE_CARLO_SAMPLES``) is small
enough to stay well under the per-tick budget but large enough to be
stable around 5 / 95 percentiles for the shapes the simulator produces.
The legacy Gaussian approximation is retained as a fallback when
``mode="gaussian"`` so a test that needs the v0.1 contract can still opt
out; it stays a single-source linear approximation.

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
from dataclasses import dataclass
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

# Design priors for the spec constants that have no estimator posterior. They
# stand for datasheet / benchmark / manufacturing tolerance, not a filtered
# belief, so the Monte Carlo bands stop treating these terms as exact (the
# model-card "single source of uncertainty" limitation). Overridable per
# profile under `self_model.priors`; a CV/sigma of 0 recovers the v0.1 band.
_DEFAULT_BATTERY_WH_CV = 0.03
_DEFAULT_TOK_PER_S_CV = 0.10
_DEFAULT_JUNCTION_THROTTLE_SIGMA_C = 1.5

QuantileMode = Literal["monte_carlo", "gaussian"]


@dataclass(frozen=True)
class _Priors:
    """Design-prior spreads for the capability inputs that lack a posterior."""

    battery_wh_cv: float
    tok_per_s_cv: float
    junction_throttle_sigma_c: float
    propagate_net_load: bool


def _priors(engine: Engine) -> _Priors:
    """Read the ``self_model.priors`` profile block, falling back to defaults.

    Profile content is attacker-influenceable configuration, so each field is
    coerced and a non-finite or negative value falls back to its default rather
    than poisoning a band.
    """
    section = engine.profile.get("self_model")
    block = section.get("priors") if isinstance(section, dict) else None
    cfg = block if isinstance(block, dict) else {}

    def _nonneg(key: str, default: float) -> float:
        raw = cfg.get(key, default)
        # A bool is not a meaningful prior spread; `float(True)` is `1.0`, which
        # would silently distort it, so reject it like any other non-numeric.
        if isinstance(raw, bool):
            return default
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        return value if math.isfinite(value) and value >= 0.0 else default

    # The flag honours a real boolean; a non-bool (e.g. a quoted "false") falls
    # back to the default (on), the safe direction since a typo then widens the
    # band rather than silently disabling propagation (ADR 0082).
    flag = cfg.get("propagate_net_load", True)
    return _Priors(
        battery_wh_cv=_nonneg("battery_wh_cv", _DEFAULT_BATTERY_WH_CV),
        tok_per_s_cv=_nonneg("tok_per_s_cv", _DEFAULT_TOK_PER_S_CV),
        junction_throttle_sigma_c=_nonneg(
            "junction_throttle_sigma_c", _DEFAULT_JUNCTION_THROTTLE_SIGMA_C
        ),
        propagate_net_load=flag if isinstance(flag, bool) else True,
    )


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
    priors = _priors(engine)
    endurance = _endurance_capability(engine, mode=mode, rng=rng, priors=priors)
    thermal_headroom = _thermal_headroom_capability(
        engine, mode=mode, rng=rng, priors=priors
    )
    inference_capacity = _inference_capacity_capability(
        engine, mode=mode, rng=rng, priors=priors
    )
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
    engine: Engine, *, mode: QuantileMode, rng: np.random.Generator, priors: _Priors
) -> Capability:
    """Endurance minutes from SoC, net load, and the inputs' posteriors.

    Net load is ``load_w - charge_accepted_w``. The Monte Carlo branch
    propagates the SoC posterior, a small ``battery_wh`` capacity-tolerance
    prior, and (by default, ADR 0082) the net load: the charge side from the
    APU total-output posterior, the variable load from the compute-draw
    posterior. Where net load is comfortably positive this simply widens the
    band; near energy balance the ``1/net_w`` term is heavy-tailed, so the
    band stays wide and the upper tail is capped conservatively at the point
    estimate (a safe understatement of the net-charging upside) rather than
    saturating. Disable with ``self_model.priors.propagate_net_load: false``
    for a SoC-and-battery-only band. When the deterministic net load is
    non-positive the battery is net-charged and endurance is unbounded; we
    return the 24 h sentinel with ``confidence=0`` so the controller treats
    it as a hint, not a hard bound.
    """
    power = engine.power
    estimate = engine.power_est.state()

    point_soc = float(estimate.point.get("soc_pct", power.soc_pct))
    soc_var = float(estimate.covariance.get("soc_pct", 0.0))
    soc_sigma = math.sqrt(max(0.0, soc_var))

    # Load is read from the power estimator's belief (ADR 0083), not ground
    # truth: a well-known input the filter tracks tightly, so endurance reasons
    # from the same belief surface as SoC and the band stays SoC-responsive near
    # energy balance. Charge stays on the APU posterior.
    load_w = float(estimate.point.get("load_w", power.truth().get("load_w", 0.0)))
    charge_w = float(power.truth().get("charge_accepted_w", 0.0))
    net_w = load_w - charge_w
    battery_wh = float(power.profile.get("power", {}).get("battery_wh", 0.0))

    load_sigma = math.sqrt(max(0.0, float(estimate.covariance.get("load_w", 0.0))))
    charge_sigma = math.sqrt(
        max(0.0, float(engine.apu_est.state().covariance.get("total_w", 0.0)))
    )

    point_min = _endurance_min(battery_wh, point_soc, net_w)

    if mode == "monte_carlo" and soc_sigma > 0.0 and net_w > 0.0:
        n = _MONTE_CARLO_SAMPLES
        soc_samples = np.clip(rng.normal(point_soc, soc_sigma, size=n), 0.0, 100.0)
        battery_scale = max(0.0, priors.battery_wh_cv * battery_wh)
        battery_samples = (
            rng.normal(battery_wh, battery_scale, size=n)
            if battery_scale > 0.0
            else np.full(n, battery_wh)
        )
        remaining_wh = np.clip(battery_samples, 0.0, None) * soc_samples / 100.0
        if priors.propagate_net_load:
            # The charge side carries the APU total-output posterior, the
            # variable load the power load_w posterior (ADR 0083; on by default,
            # ADR 0082). Near energy balance the 1/net_w term is heavy-tailed, so a
            # net-charging draw and the explosive tail are capped at the
            # deterministic point estimate: a conservative bound that keeps the
            # band wide without saturating it, so p95 never exceeds the point,
            # at the cost of understating the net-charging upside.
            sentinel = point_min
            net_samples = rng.normal(load_w, load_sigma, size=n) - rng.normal(
                charge_w, charge_sigma, size=n
            )
            with np.errstate(divide="ignore", invalid="ignore"):
                endurance_samples = np.where(
                    net_samples > 0.0, remaining_wh / net_samples * 60.0, sentinel
                )
            endurance_samples = np.clip(endurance_samples, 0.0, sentinel)
        else:
            endurance_samples = remaining_wh / net_w * 60.0
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
        drivers = ["power", "apu"] if priors.propagate_net_load else ["power"]

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
    engine: Engine, *, mode: QuantileMode, rng: np.random.Generator, priors: _Priors
) -> Capability:
    """Degrees Celsius headroom to the junction throttle threshold.

    The Monte Carlo branch samples the junction-temperature posterior and a
    small design prior on the throttle threshold itself (a datasheet constant
    with tolerance, not a filtered belief), so the band no longer treats the
    threshold as exact.
    """
    thermal = engine.thermal
    estimate = engine.thermal_est.state()

    junction_point = float(estimate.point.get("junction_c", thermal.junction_c))
    junction_var = float(estimate.covariance.get("junction_c", 0.0))
    junction_sigma = math.sqrt(max(0.0, junction_var))

    throttle_c = thermal.junction_temp_throttle
    throttle_sigma = priors.junction_throttle_sigma_c
    point_c = throttle_c - junction_point

    if mode == "monte_carlo" and (junction_sigma > 0.0 or throttle_sigma > 0.0):
        n = _MONTE_CARLO_SAMPLES
        junction_samples = rng.normal(junction_point, junction_sigma, size=n)
        throttle_samples = (
            rng.normal(throttle_c, throttle_sigma, size=n)
            if throttle_sigma > 0.0
            else np.full(n, throttle_c)
        )
        headroom_samples = throttle_samples - junction_samples
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
    engine: Engine, *, mode: QuantileMode, rng: np.random.Generator, priors: _Priors
) -> Capability:
    """Tokens-per-second the compute subsystem can sustain right now.

    The headline figure is the profile's
    ``compute.inference_local.tok_per_s_p50`` derated by the fraction of
    compute headroom still available after thermal throttling. The Monte Carlo
    branch samples the compute load-pct posterior and a design prior on the
    benchmark token rate (a published-benchmark estimate, not a measured rate
    on this device), so the band reflects both the load and the rate tolerance.
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
    capacity_sigma = priors.tok_per_s_cv * capacity

    headroom = max(0.0, 100.0 - load_point) / 100.0
    point = capacity * headroom

    if mode == "monte_carlo" and (load_sigma > 0.0 or capacity_sigma > 0.0):
        n = _MONTE_CARLO_SAMPLES
        load_samples = np.clip(rng.normal(load_point, load_sigma, size=n), 0.0, 100.0)
        headroom_samples = (100.0 - load_samples) / 100.0
        capacity_samples = (
            np.clip(rng.normal(capacity, capacity_sigma, size=n), 0.0, None)
            if capacity_sigma > 0.0
            else np.full(n, capacity)
        )
        sustained_samples = capacity_samples * headroom_samples
        p5, p50, p95 = _quantiles(sustained_samples)
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

    # Clamp the headline to the same [0, MAX] domain the samples and p95 cap use,
    # so the whole band stays consistent if a profile's R0 or the posterior drifts.
    point = min(max(0.0, eo_point, ir_point), _PERCEPTION_RANGE_MAX_M)
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
