"""Thermal Kalman filter (junction + ambient) -- stub."""

from __future__ import annotations

from ..types import Estimate, Observation

__all__ = ["ThermalKalman"]


class ThermalKalman:
    """BL-028. Linear Kalman filter over a two-state thermal model."""

    name: str = "thermal"

    def __init__(self) -> None:
        self._t = 0.0
        self._junction_c = 45.0
        self._ambient_c = 25.0

    def predict(self, dt: float) -> None:
        self._t += dt

    def update(self, obs: Observation) -> None:
        if "junction_c" in obs.payload:
            self._junction_c = float(obs.payload["junction_c"])
        if "ambient_c" in obs.payload:
            self._ambient_c = float(obs.payload["ambient_c"])

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={"junction_c": self._junction_c, "ambient_c": self._ambient_c},
            covariance={"junction_c": 1.0, "ambient_c": 0.25},
        )
