"""Comms subsystem (radios, link envelopes, RSSI, throughput) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["CommsSubsystem"]


class CommsSubsystem:
    """BL-012. Radios + link-budget model (first-order, no propagation)."""

    name: str = "comms"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {"links": [], "t": self._t}

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"links": []},
            noise={},
        )
