"""Storage subsystem (NVMe wear, free space, write rate) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["StorageSubsystem"]


class StorageSubsystem:
    """BL-008. Storage utilisation and wear curve."""

    name: str = "storage"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {"used_gib": 0.0, "wear_pct": 0.0, "t": self._t}

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"used_gib": 0.0, "wear_pct": 0.0},
            noise={},
        )
