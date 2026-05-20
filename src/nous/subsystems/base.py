"""Subsystem Protocol: ``step / truth / sensor_obs``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from ..types import Observation

__all__ = ["Subsystem"]


@runtime_checkable
class Subsystem(Protocol):
    """Interface every simulated subsystem implements.

    ``step(dt)`` advances the internal physics by ``dt`` seconds.
    ``truth()`` exposes the ground-truth state (what the simulator knows
    that an estimator cannot). ``sensor_obs()`` produces a noisy
    :class:`Observation` of the kind the estimator consumes.
    """

    name: str

    def step(self, dt: float) -> None: ...

    def truth(self) -> Mapping[str, Any]: ...

    def sensor_obs(self) -> Observation: ...
