"""Thermal envelope (compute junction, ambient, enclosure) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["ThermalSubsystem"]


class ThermalSubsystem:
    """BL-005. Thermal model coupling compute load to junction temperature."""

    name: str = "thermal"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0
        self._junction_c = 45.0
        self._ambient_c = 25.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {"junction_c": self._junction_c, "ambient_c": self._ambient_c, "t": self._t}

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"junction_c": self._junction_c, "ambient_c": self._ambient_c},
            noise={"junction_c_sigma": 1.0, "ambient_c_sigma": 0.5},
        )
