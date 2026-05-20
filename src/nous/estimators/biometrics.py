"""Biometrics Kalman filter -- stub."""

from __future__ import annotations

from ..types import Estimate, Observation

__all__ = ["BiometricsKalman"]


class BiometricsKalman:
    """BL-029. Kalman filter on heart rate, core temperature, cognitive load."""

    name: str = "biometrics"

    def __init__(self) -> None:
        self._t = 0.0
        self._point: dict[str, float] = {
            "heart_rate_bpm": 70.0,
            "core_temp_c": 37.0,
            "cognitive_load": 0.2,
        }

    def predict(self, dt: float) -> None:
        self._t += dt

    def update(self, obs: Observation) -> None:
        for key, value in obs.payload.items():
            if key in self._point and isinstance(value, (int, float)):
                self._point[key] = float(value)

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point=dict(self._point),
            covariance={"heart_rate_bpm": 4.0, "core_temp_c": 0.0025, "cognitive_load": 0.01},
        )
