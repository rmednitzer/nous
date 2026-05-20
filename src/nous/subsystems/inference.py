"""Inference subsystem (local + cloud paths) -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["InferenceSubsystem"]


class InferenceSubsystem:
    """BL-013. Mock local inference + plumbing for cloud calls."""

    name: str = "inference"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        self._t = 0.0
        self._local_calls = 0
        self._cloud_calls = 0

    def step(self, dt: float) -> None:
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {
            "local_calls": self._local_calls,
            "cloud_calls": self._cloud_calls,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "local_calls": self._local_calls,
                "cloud_calls": self._cloud_calls,
            },
            noise={},
        )
