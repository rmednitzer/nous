"""Auxiliary power unit (solar + fuel cell) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["ApuSubsystem"]


class ApuSubsystem:
    """BL-005a. Models solar harvesting and fuel-cell output."""

    name: str = "apu"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {"solar_w": 0.0, "fuelcell_w": 0.0, "t": self._t}

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"solar_w": 0.0, "fuelcell_w": 0.0},
            noise={"solar_w_sigma": 1.0, "fuelcell_w_sigma": 1.0},
        )
