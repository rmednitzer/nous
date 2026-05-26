"""Integration smoke tests for the canonical scenario pack (BL-014 + BL-023).

Walks every YAML under ``scenarios/`` against the live engine and
asserts that the runner produces a sane report (no crashes, at least
the first step fires, snapshot is well-formed). Catches regressions in
the loader, the injectors, the runner, and the subsystem mutators they
hit -- a wide net that fires loud when any leg breaks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine
from nous.scenarios import load_scenario_file, run_scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "scenarios"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.yaml"))


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    return eng


@pytest.mark.parametrize("scenario_file", SCENARIO_FILES, ids=lambda p: p.stem)
def test_canonical_scenario_runs(engine: Engine, scenario_file: Path) -> None:
    scenario = load_scenario_file(scenario_file)
    scenario_run = scenario.model_copy(update={"tick_budget": 20})
    report = run_scenario(engine, scenario_run)
    assert report["ticks_run"] >= 1
    assert report["snapshot"]["tick"] >= 1
    assert report["steps_total"] == len(scenario_run.steps)
    if scenario_run.steps and scenario_run.steps[0].at_min == 0.0:
        first = next(
            (r for r in report["records"] if r["index"] == 0), None
        )
        assert first is not None
        assert first["applied"] is True


def test_at_least_one_canonical_scenario() -> None:
    assert SCENARIO_FILES, "no scenario YAML files found under scenarios/"


def test_scenarios_share_default_profile() -> None:
    for path in SCENARIO_FILES:
        scenario = load_scenario_file(path)
        assert scenario.profile == "jetson-agx-orin"
