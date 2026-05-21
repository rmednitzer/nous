"""Biometrics Kalman filter -- stub.

The full implementation lands with BL-029. This v0.1 build validates
its inputs against physiologically plausible bounds. An out-of-range
observation is logged via :attr:`rejected_updates` but does not poison
the central estimate; predict-only behaviour then widens the covariance
until a valid reading arrives.
"""

from __future__ import annotations

import math

from ..types import Estimate, Observation

__all__ = ["BiometricsKalman"]


_BOUNDS: dict[str, tuple[float, float]] = {
    "heart_rate_bpm": (20.0, 240.0),
    "core_temp_c": (28.0, 44.0),
    "cognitive_load": (0.0, 1.0),
}
_PROCESS_SIGMA: dict[str, float] = {
    "heart_rate_bpm": 1.0,
    "core_temp_c": 0.01,
    "cognitive_load": 0.05,
}


class BiometricsKalman:
    """BL-029. Kalman filter on heart rate, core temperature, cognitive load."""

    name: str = "biometrics"

    def __init__(self) -> None:
        self._t = 0.0
        self._point: dict[str, float] = {
            "heart_rate_bpm": 70.0,
            "core_temp_c": 37.0,
            "cognitive_load": 0.2,
        }
        self._var: dict[str, float] = {
            "heart_rate_bpm": 4.0,
            "core_temp_c": 0.0025,
            "cognitive_load": 0.01,
        }
        self._rejected = 0

    @property
    def rejected_updates(self) -> int:
        return self._rejected

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        for key, sigma in _PROCESS_SIGMA.items():
            self._var[key] += (sigma**2) * dt

    def update(self, obs: Observation) -> None:
        for key, raw in obs.payload.items():
            if key not in _BOUNDS:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                self._rejected += 1
                continue
            lo, hi = _BOUNDS[key]
            if not math.isfinite(v) or not lo <= v <= hi:
                self._rejected += 1
                continue
            sigma = float(obs.noise.get(f"{key}_sigma", 0.0)) ** 2
            if sigma > 0.0:
                denom = self._var[key] + sigma
                k = self._var[key] / denom
                self._point[key] = (1.0 - k) * self._point[key] + k * v
                self._var[key] = (1.0 - k) * self._var[key]
            else:
                self._point[key] = v
        self._t = float(obs.ts_s)

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point=dict(self._point),
            covariance=dict(self._var),
        )
