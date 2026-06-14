"""Innovation gating and health tracking for the scalar Kalman estimators.

Every per-channel filter in this package shares one recursion: a prior
variance grows under process noise, a measurement folds in through a Kalman
gain, and the posterior variance shrinks. Each estimator used to open-code
that recursion and expose only a mean and a variance, so a controller could
not tell whether a filter had just rejected a wild reading, how consistent
its measurements were, or whether its variance had quietly collapsed to a
falsely certain zero.

:class:`ScalarChannel` centralises the recursion and adds the diagnostics a
real EKF publishes (the shape of PX4's ``estimator_status``): a normalised
innovation squared (NIS) gate that rejects a measurement inconsistent with
the current belief, an exponentially weighted *signed* test ratio so a
persistently biased sensor is legible before it trips the gate, a variance
floor so the posterior never claims more certainty than the sensor can
support, and a reset path that re-seeds the channel from a *sustained*
disagreement rather than rejecting it forever.

The gate is skipped on a channel's first fusion. An unconstrained filter must
seed itself from its first measurement, exactly as an EKF initialises
position from its first fix; gating only earns its keep once the channel
holds a belief worth defending. A single outlier is rejected; a shift that
persists for ``reset_after`` updates is adopted through a reset (a legible
event, counted in ``reset_count``) instead of being fought indefinitely.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from ..types import EstimatorHealth

__all__ = ["ChannelSpec", "ScalarChannel", "build_health", "parse_bounded"]

# Smoothing for the signed test-ratio low-pass. Tuned so a sensor sitting just
# inside the gate still surfaces within a handful of ticks without a single
# spike dominating the trace.
_TEST_RATIO_SMOOTHING = 0.2

# Consecutive gate rejections before a channel is reported unhealthy. One
# rejection is an outlier; a run of them is a divergence the controller must
# see even when the reset path has not yet adopted the new value.
_UNHEALTHY_CONSECUTIVE_REJECTS = 3


@dataclass(frozen=True)
class ChannelSpec:
    """Per-channel tuning for process noise, the gate, the floor, and reset.

    ``gate_sigma`` is a sigma multiplier: a measurement is rejected when its
    innovation exceeds ``gate_sigma`` standard deviations of the innovation
    variance. ``var_floor`` is the smallest posterior variance the channel
    will report, so a converged filter stays honest about residual sensor
    noise. ``reset_after`` is the number of consecutive rejections that
    triggers adoption of the disputed value; ``0`` disables reset and the
    channel will reject a sustained shift forever.
    """

    process_var_per_s: float = 0.0
    gate_sigma: float = 5.0
    var_floor: float = 1e-9
    reset_after: int = 3
    reset_var: float | None = None


class ScalarChannel:
    """One scalar state with a gated Kalman update and health bookkeeping."""

    __slots__ = (
        "_consec_reject",
        "_fused_ever",
        "_init_var",
        "fused",
        "innovation",
        "rejected",
        "resets",
        "spec",
        "test_ratio",
        "test_ratio_filtered",
        "value",
        "var",
    )

    def __init__(
        self, value: float, var: float, spec: ChannelSpec | None = None
    ) -> None:
        self.spec = spec if spec is not None else ChannelSpec()
        self.value = float(value)
        self.var = float(var)
        self._init_var = float(var)
        self.innovation = 0.0
        self.test_ratio = 0.0
        self.test_ratio_filtered = 0.0
        self.rejected = 0
        self.resets = 0
        self.fused = False
        self._fused_ever = False
        self._consec_reject = 0

    @property
    def diverging(self) -> bool:
        """True once gate rejections have run long enough to flag the channel."""
        return self._consec_reject >= _UNHEALTHY_CONSECUTIVE_REJECTS

    def predict(self, dt: float) -> None:
        if dt > 0.0:
            self.var += self.spec.process_var_per_s * dt

    def fuse(self, z: float, r: float) -> bool:
        """Fold a measurement ``z`` with variance ``r``; return whether accepted."""
        return self.fuse_innovation(z - self.value, r)

    def fuse_innovation(self, innovation: float, r: float) -> bool:
        """Fuse a pre-computed innovation (lets callers wrap angular residuals)."""
        if r <= 0.0:
            # A noiseless observation: adopt it and collapse to the floor.
            self._apply(innovation, posterior_var=self.spec.var_floor)
            self.test_ratio = 0.0
            return True

        s = self.var + r
        if not math.isfinite(innovation) or not math.isfinite(s) or s <= 0.0:
            self._count_rejection()
            return False

        test_ratio = (innovation * innovation) / (self.spec.gate_sigma**2 * s)
        self.test_ratio = test_ratio
        signed = math.copysign(test_ratio, innovation) if innovation != 0.0 else 0.0
        self.test_ratio_filtered += _TEST_RATIO_SMOOTHING * (
            signed - self.test_ratio_filtered
        )

        if self._fused_ever and (test_ratio > 1.0 or not math.isfinite(test_ratio)):
            return self._reject_or_reset(innovation)

        k = self.var / s
        self._apply(innovation, posterior_var=(1.0 - k) * self.var, gain=k)
        return True

    def _apply(
        self, innovation: float, *, posterior_var: float, gain: float = 1.0
    ) -> None:
        self.value += gain * innovation
        self.var = max(self.spec.var_floor, posterior_var)
        self.innovation = innovation
        self.fused = True
        self._fused_ever = True
        self._consec_reject = 0

    def _count_rejection(self) -> None:
        self.rejected += 1
        self._consec_reject += 1
        self.fused = False

    def _reject_or_reset(self, innovation: float) -> bool:
        self._count_rejection()
        spec = self.spec
        if spec.reset_after > 0 and self._consec_reject >= spec.reset_after:
            reset_var = spec.reset_var if spec.reset_var is not None else self._init_var
            self.value += innovation
            self.var = max(spec.var_floor, reset_var)
            self.innovation = innovation
            self.resets += 1
            self._consec_reject = 0
            self.fused = True
            return True
        return False


def parse_bounded(raw: object, lo: float, hi: float) -> float | None:
    """Return ``raw`` as a finite float inside ``[lo, hi]``, else ``None``.

    The shared input-validation gate for the bounded estimators: a value that
    is non-numeric, non-finite, or physically implausible is refused before it
    reaches the filter, where it would be counted as a rejection rather than
    fused.
    """
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or not lo <= value <= hi:
        return None
    return value


def build_health(
    channels: Mapping[str, ScalarChannel],
    *,
    rejected_extra: int = 0,
    reset_extra: int = 0,
    dead_reckoning: bool = False,
    fused_override: bool | None = None,
    healthy_override: bool | None = None,
) -> EstimatorHealth:
    """Assemble an :class:`~nous.types.EstimatorHealth` from a channel set.

    ``rejected_extra`` / ``reset_extra`` fold in rejections counted outside the
    channels (input-validation failures, particle-weight collapse). A channel's
    ``fused`` flag is sticky (it holds the last fusion result), so an estimator
    that may skip fusion on a tick (a position filter with no fix) passes
    ``fused_override`` to report whether *this* update fused. ``healthy_override``
    lets an estimator AND in its own fault signal; the channel-level divergence
    flag is always honoured on top of it.
    """
    rejected = rejected_extra + sum(c.rejected for c in channels.values())
    resets = reset_extra + sum(c.resets for c in channels.values())
    diverging = any(c.diverging for c in channels.values())
    if fused_override is not None:
        fused = fused_override
    else:
        fused = any(c.fused for c in channels.values()) if channels else True
    healthy = not diverging if healthy_override is None else healthy_override and not diverging
    return EstimatorHealth(
        healthy=healthy,
        fused=fused,
        dead_reckoning=dead_reckoning,
        rejected_updates=rejected,
        reset_count=resets,
        test_ratio={k: round(c.test_ratio, 6) for k, c in channels.items()},
        test_ratio_filtered={
            k: round(c.test_ratio_filtered, 6) for k, c in channels.items()
        },
        innovation={k: round(c.innovation, 6) for k, c in channels.items()},
    )
