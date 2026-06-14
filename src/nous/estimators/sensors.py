"""Environmental sensor Kalman filter (BL-009).

Per-channel scalar Kalman over (temp_c, humidity_pct, baro_kpa). The
environmental pack is slowly varying under typical mission profiles, so the
per-second process variance is small; each channel folds the observation
through a gated Kalman update sized by the profile's advertised sigmas,
floors its posterior variance, and resyncs its clock to ``obs.ts_s``.

Out-of-range or non-finite readings are refused before the filter sees them
(matching the validation contract of
:class:`~nous.estimators.position.PositionKalman` and
:class:`~nous.estimators.biometrics.BiometricsKalman`) and counted as
rejections in the health block.
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health, parse_bounded

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
    """Gated scalar Kalman per channel over (temp_c, humidity_pct, baro_kpa)."""

    name: str = "sensors"

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
