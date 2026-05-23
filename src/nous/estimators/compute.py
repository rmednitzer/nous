"""Compute Kalman filter over load fraction and electrical draw.

A linear Kalman filter over the two scalars the compute subsystem
reports (BL-031a is the full multi-state EKF). Predict inflates the
per-channel variance with elapsed time; update folds the noisy
observation toward the prior via a Kalman gain and resynchronises the
estimator clock to ``obs.ts_s`` (matching the PowerEstimator and
ThermalKalman contracts).
"""

from __future__ import annotations

import math

from ..types import Estimate, Observation

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
    """1-D scalar Kalman filter over (load_pct, draw_w)."""

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
        self._load_pct = float(initial_load_pct)
        self._draw_w = float(initial_draw_w)
        self._var_load = float(load_sigma) ** 2
        self._var_draw = float(draw_sigma) ** 2

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        self._var_load += _LOAD_PROCESS_VARIANCE_PER_S * dt
        self._var_draw += _DRAW_PROCESS_VARIANCE_PER_S * dt

    def update(self, obs: Observation) -> None:
        noise = obs.noise or {}
        if "load_pct" in obs.payload:
            r = float(noise.get("load_pct_sigma", _FALLBACK_LOAD_SIGMA)) ** 2
            k = self._var_load / (self._var_load + max(r, 1e-6))
            self._load_pct = self._load_pct + k * (
                float(obs.payload["load_pct"]) - self._load_pct
            )
            self._var_load = (1.0 - k) * self._var_load
        if "draw_w" in obs.payload:
            r = float(noise.get("draw_w_sigma", _FALLBACK_DRAW_SIGMA)) ** 2
            k = self._var_draw / (self._var_draw + max(r, 1e-6))
            self._draw_w = self._draw_w + k * (
                float(obs.payload["draw_w"]) - self._draw_w
            )
            self._var_draw = (1.0 - k) * self._var_draw
        try:
            ts = float(obs.ts_s)
        except (TypeError, ValueError):
            return
        if math.isfinite(ts) and ts >= 0.0:
            self._t = ts

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={"load_pct": self._load_pct, "draw_w": self._draw_w},
            covariance={"load_pct": self._var_load, "draw_w": self._var_draw},
        )
