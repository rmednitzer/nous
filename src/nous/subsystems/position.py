"""Position / IMU subsystem (GNSS + 9-DoF IMU) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["PositionSubsystem"]


class PositionSubsystem:
    """BL-010. GNSS + IMU fusion source for the position EKF."""

    name: str = "position"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0
        self._lat = 47.0
        self._lon = 13.0
        self._alt_m = 500.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {"lat": self._lat, "lon": self._lon, "alt_m": self._alt_m, "t": self._t}

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"lat": self._lat, "lon": self._lon, "alt_m": self._alt_m},
            noise={"lat_sigma": 3e-5, "lon_sigma": 3e-5, "alt_m_sigma": 5.0},
        )
