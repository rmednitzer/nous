"""Position EKF over GNSS + IMU -- stub."""

from __future__ import annotations

from ..types import Estimate, Observation

__all__ = ["PositionEKF"]


class PositionEKF:
    """BL-026. Extended Kalman filter on a constant-velocity kinematic model."""

    name: str = "position"

    def __init__(self) -> None:
        self._t = 0.0
        self._point: dict[str, float] = {"lat": 0.0, "lon": 0.0, "alt_m": 0.0}

    def predict(self, dt: float) -> None:
        self._t += dt

    def update(self, obs: Observation) -> None:
        for key in ("lat", "lon", "alt_m"):
            if key in obs.payload:
                self._point[key] = float(obs.payload[key])

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point=dict(self._point),
            covariance={"lat": 1e-10, "lon": 1e-10, "alt_m": 1.0},
        )
