"""Environmental sensor Kalman filter (BL-009).

Multi-channel 1-D Kalman over (temp_c, humidity_pct, baro_kpa). The
environmental sensor pack is slowly varying under typical mission
profiles, so per-second process variance is small; the filter folds
the noisy observation toward the prior via a Kalman gain sized by the
profile's advertised sigmas and resyncs its clock to ``obs.ts_s``.

Out-of-range or non-finite readings are rejected without poisoning
the central estimate (matches the validation contract from
:class:`~nous.estimators.position.PositionKalman` and
:class:`~nous.estimators.biometrics.BiometricsKalman`).
"""

from __future__ import annotations

import math

from ..types import Estimate, Observation

__all__ = ["EnvironmentalKalman"]


_BOUNDS: dict[str, tuple[float, float]] = {
    "temp_c": (-90.0, 90.0),
    "humidity_pct": (0.0, 100.0),
    "baro_kpa": (10.0, 200.0),
}
_PROCESS_SIGMA: dict[str, float] = {
    "temp_c": 0.05,
    "humidity_pct": 0.2,
    "baro_kpa": 0.05,
}
_INITIAL_VAR: dict[str, float] = {
    "temp_c": 1.0,
    "humidity_pct": 10.0,
    "baro_kpa": 1.0,
}
_INITIAL_POINT: dict[str, float] = {
    "temp_c": 22.0,
    "humidity_pct": 50.0,
    "baro_kpa": 101.3,
}


class EnvironmentalKalman:
    """1-D Kalman per channel over (temp_c, humidity_pct, baro_kpa)."""

    name: str = "sensors"

    def __init__(self) -> None:
        self._t = 0.0
        self._point: dict[str, float] = dict(_INITIAL_POINT)
        self._var: dict[str, float] = dict(_INITIAL_VAR)
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
            r = float(obs.noise.get(f"{key}_sigma", 0.0)) ** 2
            if r > 0.0:
                denom = self._var[key] + r
                k = self._var[key] / denom
                self._point[key] = (1.0 - k) * self._point[key] + k * v
                self._var[key] = (1.0 - k) * self._var[key]
            else:
                self._point[key] = v
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
            point=dict(self._point),
            covariance=dict(self._var),
        )
