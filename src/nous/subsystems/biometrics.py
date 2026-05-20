"""Operator biometrics (HR, core temp, hydration, cognitive load proxy) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["BiometricsSubsystem"]


class BiometricsSubsystem:
    """BL-011. Parametric biometrics; not a physiology-grounded model (L2)."""

    name: str = "biometrics"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {
            "heart_rate_bpm": 70.0,
            "core_temp_c": 37.0,
            "hydration_pct": 90.0,
            "cognitive_load": 0.2,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "heart_rate_bpm": 70.0,
                "core_temp_c": 37.0,
                "hydration_pct": 90.0,
                "cognitive_load": 0.2,
            },
            noise={
                "heart_rate_bpm_sigma": 2.0,
                "core_temp_c_sigma": 0.05,
            },
        )
