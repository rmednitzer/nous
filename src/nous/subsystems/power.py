"""Battery (Li-ion with Peukert correction and thermal derate) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["PowerSubsystem"]


class PowerSubsystem:
    """BL-003. Battery state model. Curves come from the hardware profile."""

    name: str = "power"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0
        self._soc_pct = 100.0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {"soc_pct": self._soc_pct, "t": self._t}

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"soc_pct": self._soc_pct},
            noise={"soc_pct_sigma": 0.5},
        )
