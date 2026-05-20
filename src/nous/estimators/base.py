"""Estimator Protocol: ``predict / update / state``."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..types import Estimate, Observation

__all__ = ["Estimator"]


@runtime_checkable
class Estimator(Protocol):
    """Recursive belief over a subsystem's hidden state.

    ``predict(dt)`` advances the filter by ``dt`` without an observation.
    ``update(obs)`` folds in a new :class:`Observation`. ``state()``
    returns the current :class:`Estimate`.
    """

    name: str

    def predict(self, dt: float) -> None: ...

    def update(self, obs: Observation) -> None: ...

    def state(self) -> Estimate: ...
