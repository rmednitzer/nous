"""Biometrics Kalman filter (BL-029).

A live multi-channel scalar Kalman over heart rate, core temperature,
hydration, and cognitive load. The build validates inputs against
physiologically plausible bounds: an out-of-range observation is counted in
the health block (and exposed via :attr:`rejected_updates`) but does not
poison the central estimate. Each in-range reading folds in through a gated
Kalman update that rejects a value inconsistent with the current belief,
floors the posterior variance, and adopts a sustained shift through a reset
(see :mod:`nous.estimators.health`). The full physiological-dynamics model
lands with BL-029.
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health, parse_bounded

__all__ = ["BiometricsKalman"]


_BOUNDS: dict[str, tuple[float, float]] = {
    "heart_rate_bpm": (20.0, 240.0),
    "core_temp_c": (28.0, 44.0),
    "hydration_pct": (0.0, 100.0),
    "cognitive_load": (0.0, 1.0),
}
_PROCESS_SIGMA: dict[str, float] = {
    "heart_rate_bpm": 1.0,
    "core_temp_c": 0.01,
    "hydration_pct": 0.1,
    "cognitive_load": 0.05,
}
_INITIAL_POINT: dict[str, float] = {
    "heart_rate_bpm": 70.0,
    "core_temp_c": 37.0,
    "hydration_pct": 90.0,
    "cognitive_load": 0.2,
}
_INITIAL_VAR: dict[str, float] = {
    "heart_rate_bpm": 4.0,
    "core_temp_c": 0.0025,
    "hydration_pct": 4.0,
    "cognitive_load": 0.01,
}


class BiometricsKalman:
    """Gated scalar Kalman on heart rate, core temperature, hydration, load."""

    name: str = "biometrics"

    def __init__(self) -> None:
        self._t = 0.0
        self._rejected = 0
        self._channels: dict[str, ScalarChannel] = {
            key: ScalarChannel(
                _INITIAL_POINT[key],
                _INITIAL_VAR[key],
                ChannelSpec(process_var_per_s=_PROCESS_SIGMA[key] ** 2),
            )
            for key in _BOUNDS
        }

    @property
    def rejected_updates(self) -> int:
        return self._rejected

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        for channel in self._channels.values():
            channel.predict(dt)

    def update(self, obs: Observation) -> None:
        for key, channel in self._channels.items():
            if key not in obs.payload:
                continue
            lo, hi = _BOUNDS[key]
            z = parse_bounded(obs.payload[key], lo, hi)
            if z is None:
                self._rejected += 1
                continue
            r = float(obs.noise.get(f"{key}_sigma", 0.0)) ** 2
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
