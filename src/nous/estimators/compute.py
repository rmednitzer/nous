"""Compute-load Kalman filter -- stub."""

from __future__ import annotations

from ..types import Estimate, Observation

__all__ = ["ComputeKalman"]


class ComputeKalman:
    """BL-031a. Kalman filter on load percentage and draw watts."""

    name: str = "compute"

    def __init__(self) -> None:
        self._t = 0.0
        self._load_pct = 5.0
        self._draw_w = 8.0

    def predict(self, dt: float) -> None:
        self._t += dt

    def update(self, obs: Observation) -> None:
        if "load_pct" in obs.payload:
            self._load_pct = float(obs.payload["load_pct"])
        if "draw_w" in obs.payload:
            self._draw_w = float(obs.payload["draw_w"])

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={"load_pct": self._load_pct, "draw_w": self._draw_w},
            covariance={"load_pct": 2.0, "draw_w": 0.25},
        )
