"""Position EKF over GNSS + IMU -- stub.

The full implementation lands with BL-026. This v0.1 build is a
pass-through estimator that *validates* its inputs: NaN, Inf, and
out-of-range lat/lon are rejected so a corrupted sensor reading cannot
poison the downstream self-model. Validation refusals grow the
covariance via :meth:`predict`, mimicking the divergence a real EKF
would surface to the controller.
"""

from __future__ import annotations

import math

from ..types import Estimate, Observation

__all__ = ["PositionEKF"]


_INIT_LAT_SIGMA = 5e-5
_INIT_LON_SIGMA = 5e-5
_INIT_ALT_SIGMA = 1.0
_PROCESS_SIGMA_PER_S = 1e-6
_PROCESS_ALT_SIGMA_PER_S = 0.01


class PositionEKF:
    """BL-026. Extended Kalman filter on a constant-velocity kinematic model."""

    name: str = "position"

    def __init__(self) -> None:
        self._t = 0.0
        self._point: dict[str, float] = {"lat": 0.0, "lon": 0.0, "alt_m": 0.0}
        self._var: dict[str, float] = {
            "lat": _INIT_LAT_SIGMA**2,
            "lon": _INIT_LON_SIGMA**2,
            "alt_m": _INIT_ALT_SIGMA**2,
        }
        self._rejected = 0

    @property
    def rejected_updates(self) -> int:
        """Count of observations refused on input validation."""
        return self._rejected

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        self._var["lat"] += (_PROCESS_SIGMA_PER_S**2) * dt
        self._var["lon"] += (_PROCESS_SIGMA_PER_S**2) * dt
        self._var["alt_m"] += (_PROCESS_ALT_SIGMA_PER_S**2) * dt

    def update(self, obs: Observation) -> None:
        if not _validate(obs.payload):
            self._rejected += 1
            return
        for key in ("lat", "lon", "alt_m"):
            if key in obs.payload:
                self._point[key] = float(obs.payload[key])
                sigma = float(obs.noise.get(f"{key}_sigma", 0.0)) ** 2
                if sigma > 0.0:
                    denom = self._var[key] + sigma
                    k = self._var[key] / denom
                    self._var[key] = (1.0 - k) * self._var[key]
        self._t = float(obs.ts_s)

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point=dict(self._point),
            covariance=dict(self._var),
        )


def _validate(payload: dict[str, object]) -> bool:
    """Reject NaN/Inf and out-of-range lat/lon/alt before the filter eats them."""
    for key, value in payload.items():
        if key not in ("lat", "lon", "alt_m"):
            continue
        try:
            v = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if not math.isfinite(v):
            return False
        if key == "lat" and not -90.0 <= v <= 90.0:
            return False
        if key == "lon" and not -180.0 <= v <= 180.0:
            return False
        if key == "alt_m" and not -1000.0 <= v <= 100_000.0:
            return False
    return True
