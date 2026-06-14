"""Storage Kalman filter over (used_gib, wear_pct).

A scalar Kalman filter over the two values the storage subsystem reports.
Wear and used-space are slowly varying, so the per-channel process variance
is small and the filter is dominated by the observation when updates are
available. Each channel gates inconsistent readings, floors its posterior
variance, and adopts a sustained shift through a reset (see
:mod:`nous.estimators.health`).
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health

__all__ = ["StorageKalman"]


_DEFAULT_USED_SIGMA = 1.0
_DEFAULT_WEAR_SIGMA = 1.0
_USED_PROCESS_VARIANCE_PER_S = 0.001
_WEAR_PROCESS_VARIANCE_PER_S = 0.0001
_FALLBACK_USED_SIGMA = 0.05
_FALLBACK_WEAR_SIGMA = 0.1


class StorageKalman:
    """Gated scalar Kalman filter over (used_gib, wear_pct)."""

    name: str = "storage"

    def __init__(
        self,
        *,
        initial_used_gib: float = 0.0,
        initial_wear_pct: float = 0.0,
        used_sigma: float = _DEFAULT_USED_SIGMA,
        wear_sigma: float = _DEFAULT_WEAR_SIGMA,
    ) -> None:
        self._t = 0.0
        self._rejected = 0
        self._fallback: dict[str, float] = {
            "used_gib": _FALLBACK_USED_SIGMA,
            "wear_pct": _FALLBACK_WEAR_SIGMA,
        }
        self._channels: dict[str, ScalarChannel] = {
            "used_gib": ScalarChannel(
                float(initial_used_gib),
                float(used_sigma) ** 2,
                ChannelSpec(process_var_per_s=_USED_PROCESS_VARIANCE_PER_S),
            ),
            "wear_pct": ScalarChannel(
                float(initial_wear_pct),
                float(wear_sigma) ** 2,
                ChannelSpec(process_var_per_s=_WEAR_PROCESS_VARIANCE_PER_S),
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
