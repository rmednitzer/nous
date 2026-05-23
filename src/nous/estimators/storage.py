"""Storage Kalman filter over (used_gib, wear_pct).

A linear Kalman filter over the two scalars the storage subsystem
reports. Wear and used-space are slowly varying quantities; the
per-channel process variance per second is correspondingly small so
the filter is dominated by the observation when sensor updates are
available, and decays gracefully toward the prior when they are not.
"""

from __future__ import annotations

import math

from ..types import Estimate, Observation

__all__ = ["StorageKalman"]


_DEFAULT_USED_SIGMA = 1.0
_DEFAULT_WEAR_SIGMA = 1.0
_USED_PROCESS_VARIANCE_PER_S = 0.001
_WEAR_PROCESS_VARIANCE_PER_S = 0.0001
_FALLBACK_USED_SIGMA = 0.05
_FALLBACK_WEAR_SIGMA = 0.1


class StorageKalman:
    """1-D scalar Kalman filter over (used_gib, wear_pct)."""

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
        self._used_gib = float(initial_used_gib)
        self._wear_pct = float(initial_wear_pct)
        self._var_used = float(used_sigma) ** 2
        self._var_wear = float(wear_sigma) ** 2

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        self._var_used += _USED_PROCESS_VARIANCE_PER_S * dt
        self._var_wear += _WEAR_PROCESS_VARIANCE_PER_S * dt

    def update(self, obs: Observation) -> None:
        noise = obs.noise or {}
        if "used_gib" in obs.payload:
            r = float(noise.get("used_gib_sigma", _FALLBACK_USED_SIGMA)) ** 2
            k = self._var_used / (self._var_used + max(r, 1e-9))
            self._used_gib = self._used_gib + k * (
                float(obs.payload["used_gib"]) - self._used_gib
            )
            self._var_used = (1.0 - k) * self._var_used
        if "wear_pct" in obs.payload:
            r = float(noise.get("wear_pct_sigma", _FALLBACK_WEAR_SIGMA)) ** 2
            k = self._var_wear / (self._var_wear + max(r, 1e-9))
            self._wear_pct = self._wear_pct + k * (
                float(obs.payload["wear_pct"]) - self._wear_pct
            )
            self._var_wear = (1.0 - k) * self._var_wear
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
            point={"used_gib": self._used_gib, "wear_pct": self._wear_pct},
            covariance={"used_gib": self._var_used, "wear_pct": self._var_wear},
        )
