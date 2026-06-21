"""EO/IR detection-range Kalman filter (BL-055).

Per-band scalar Kalman over the electro-optical and infrared effective detection
ranges. The payload reports its own range estimate each tick with a measurement
sigma that widens as the focal-plane calibration drifts, so the filter folds a
trustworthy reading hard and an untrustworthy one gently, floors its posterior
variance, and resyncs its clock to ``obs.ts_s``.

Out-of-range or non-finite readings are refused before the filter sees them
(matching the validation contract of the other channel estimators) and counted as
rejections in the health block.
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health, parse_bounded

__all__ = ["EoirKalman"]


_BOUNDS: dict[str, tuple[float, float]] = {
    "eo_range_m": (0.0, 60000.0),
    "ir_range_m": (0.0, 60000.0),
}
_PROCESS_SIGMA: dict[str, float] = {
    "eo_range_m": 50.0,
    "ir_range_m": 50.0,
}
_INITIAL_VAR: dict[str, float] = {
    "eo_range_m": 1.0e6,
    "ir_range_m": 1.0e6,
}
_INITIAL_POINT: dict[str, float] = {
    "eo_range_m": 12000.0,
    "ir_range_m": 8000.0,
}


class EoirKalman:
    """Gated scalar Kalman per band over (eo_range_m, ir_range_m)."""

    name: str = "eoir"

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
