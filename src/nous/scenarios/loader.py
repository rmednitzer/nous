"""Scenario YAML loader.

A scenario is a deterministic timeline of injected events. The loader
turns the YAML into a typed :class:`Scenario` with explicit steps; the
injectors in :mod:`nous.scenarios.injectors` mutate engine state when a
step fires.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["Scenario", "ScenarioStep", "load_scenario"]


class ScenarioStep(BaseModel):
    at_min: float
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class Scenario(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)
    profile: str = "jetson-agx-orin"
    tick_budget: int = 600
    steps: list[ScenarioStep] = Field(default_factory=list)


def load_scenario(data: Mapping[str, Any]) -> Scenario:
    """Parse a scenario YAML document into a :class:`Scenario`."""
    return Scenario.model_validate(dict(data))
