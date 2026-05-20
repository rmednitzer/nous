"""Environmental sensor pack (temperature, humidity, baro, IMU) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["SensorsSubsystem"]


class SensorsSubsystem:
    """BL-009. Environmental sensors aggregated through a single subsystem."""

    name: str = "sensors"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {"temp_c": 22.0, "humidity_pct": 50.0, "baro_kpa": 101.3, "t": self._t}

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"temp_c": 22.0, "humidity_pct": 50.0, "baro_kpa": 101.3},
            noise={"temp_c_sigma": 0.2, "humidity_pct_sigma": 1.0, "baro_kpa_sigma": 0.1},
        )
