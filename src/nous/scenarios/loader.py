"""Scenario YAML loader (BL-014).

A scenario is a deterministic timeline of injected events plus a few
controller-visible knobs (which profile to mount, how many ticks to
run for, free-form metadata for the audit trail). The loader turns
the YAML into a typed :class:`Scenario` with explicit steps; the
injectors in :mod:`nous.scenarios.injectors` mutate engine state when
the runner fires a step.

Schema:

.. code-block:: yaml

    schema_version: "0.1.0"
    meta:
      name: scenario-name
      description: Short prose explaining the scenario's purpose.
    profile: jetson-agx-orin
    tick_budget: 600
    steps:
      - { at_min: 0, action: state_transition, args: { trigger: mission } }
      - { at_min: 5, action: inject_biometrics, args: { core_temp_c_delta: 0.5 } }

Unknown actions fail in the runner, not in the loader, so a scenario
that names a new injector is loadable on an older simulator (the
runner reports the unknown action through the audit trail and skips
the step). Unknown top-level keys are tolerated by the pydantic
model so a forward-compatible field (``schema_version``,
``expectations``) does not break the load.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Scenario", "ScenarioStep", "load_scenario", "load_scenario_file"]


class ScenarioStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    at_min: float
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="allow")

    meta: dict[str, Any] = Field(default_factory=dict)
    profile: str = "jetson-agx-orin"
    tick_budget: int = Field(default=600, ge=1)
    steps: list[ScenarioStep] = Field(default_factory=list)

    @property
    def name(self) -> str:
        meta_name = self.meta.get("name") if isinstance(self.meta, Mapping) else None
        return str(meta_name) if meta_name else "scenario"

    def steps_sorted(self) -> list[ScenarioStep]:
        return sorted(self.steps, key=lambda s: (s.at_min, s.action))


def load_scenario(data: Mapping[str, Any]) -> Scenario:
    """Parse a scenario YAML mapping into a :class:`Scenario`."""
    return Scenario.model_validate(dict(data))


def load_scenario_file(path: str | Path) -> Scenario:
    """Read and parse ``path``. Empty / invalid files raise ``ValueError``."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"scenario YAML not found: {p}")
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, Mapping):
        raise ValueError(f"scenario YAML must decode to a mapping: {p}")
    return load_scenario(data)
