"""Comms particle filter over link state -- stub."""

from __future__ import annotations

from ..types import Estimate, Observation

__all__ = ["CommsParticleFilter"]


class CommsParticleFilter:
    """BL-030. Particle filter over connection state per link."""

    name: str = "comms"

    def __init__(self, particles: int = 64) -> None:
        self._t = 0.0
        self._particles = particles

    def predict(self, dt: float) -> None:
        self._t += dt

    def update(self, obs: Observation) -> None:
        return None

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={"connected_links": 0.0},
            covariance={"connected_links": 0.5},
        )
