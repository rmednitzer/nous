"""Compute Kalman filter over load fraction and electrical draw.

A scalar Kalman filter over the two values the compute subsystem reports
(BL-031a is the full multi-state EKF). Predict inflates the per-channel
variance with elapsed time; update folds the observation through a gated
Kalman step that rejects an inconsistent reading, floors the posterior
variance, and adopts a sustained load step through a reset (see
:mod:`nous.estimators.health`), then resynchronises the estimator clock to
``obs.ts_s``.
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health

__all__ = ["ComputeKalman"]


_DEFAULT_LOAD_PCT = 5.0
_DEFAULT_DRAW_W = 8.0
_DEFAULT_LOAD_SIGMA = 5.0
_DEFAULT_DRAW_SIGMA = 1.0
_LOAD_PROCESS_VARIANCE_PER_S = 0.5
_DRAW_PROCESS_VARIANCE_PER_S = 0.1
_FALLBACK_LOAD_SIGMA = 1.5
_FALLBACK_DRAW_SIGMA = 0.5


class ComputeKalman:
    """Gated scalar Kalman filter over (load_pct, draw_w)."""

    name: str = "compute"

    def __init__(
        self,
        *,
        initial_load_pct: float = _DEFAULT_LOAD_PCT,
        initial_draw_w: float = _DEFAULT_DRAW_W,
        load_sigma: float = _DEFAULT_LOAD_SIGMA,
        draw_sigma: float = _DEFAULT_DRAW_SIGMA,
    ) -> None:
        self._t = 0.0
        self._rejected = 0
        self._fallback: dict[str, float] = {
            "load_pct": _FALLBACK_LOAD_SIGMA,
            "draw_w": _FALLBACK_DRAW_SIGMA,
        }
        self._channels: dict[str, ScalarChannel] = {
            "load_pct": ScalarChannel(
                float(initial_load_pct),
                float(load_sigma) ** 2,
                ChannelSpec(process_var_per_s=_LOAD_PROCESS_VARIANCE_PER_S),
            ),
            "draw_w": ScalarChannel(
                float(initial_draw_w),
                float(draw_sigma) ** 2,
                ChannelSpec(process_var_per_s=_DRAW_PROCESS_VARIANCE_PER_S),
            ),
        }

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        for channel in self._channels.values():
            channel.predict(dt)

    def update(self, obs: Observation) -> None:
        noise = obs.noise or {}
        for key, channel in self._channels.items():
            if key not in obs.payload:
                continue
            try:
                z = float(obs.payload[key])
            except (TypeError, ValueError):
                self._rejected += 1
                continue
            if not math.isfinite(z):
                self._rejected += 1
                continue
            r = float(noise.get(f"{key}_sigma", self._fallback[key])) ** 2
            channel.fuse(z, r)
        try:
            ts = float(obs.ts_s)
        except (TypeError, ValueError):
            return
        if math.isfinite(ts) and ts >= 0.0:
            self._t = ts

    def health(self) -> EstimatorHealth:
        return build_health(self._channels, rejected_extra=self._rejected)

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={key: c.value for key, c in self._channels.items()},
            covariance={key: c.var for key, c in self._channels.items()},
            health=self.health(),
        )
