"""Compute subsystem (CPU/GPU load, power, latency) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["ComputeSubsystem"]


class ComputeSubsystem:
    """BL-007. Compute load, draw, and latency derived from profile curves."""

    name: str = "compute"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0
        self._load_pct = 5.0
        self._draw_w = 8.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {"load_pct": self._load_pct, "draw_w": self._draw_w, "t": self._t}

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"load_pct": self._load_pct, "draw_w": self._draw_w},
            noise={"load_pct_sigma": 1.5, "draw_w_sigma": 0.5},
        )
