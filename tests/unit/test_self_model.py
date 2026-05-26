"""Unit tests for the BL-018 self-model layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine
from nous.self_model.assess import assess
from nous.self_model.explain import explain
from nous.self_model.viability import viability


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    eng.tick()
    return eng


def test_assess_returns_quantile_bands(engine: Engine) -> None:
    a = assess("can we sustain inference?", engine=engine)

    assert a.endurance is not None
    assert a.thermal_headroom is not None
    assert a.inference_capacity is not None

    assert a.endurance.units == "min"
    assert a.thermal_headroom.units == "C"
    assert a.inference_capacity.units == "tok/s"

    for cap in (a.endurance, a.thermal_headroom, a.inference_capacity):
        assert cap.p5 <= cap.p50 <= cap.p95
        assert cap.drivers


def test_assess_without_engine_returns_zeros() -> None:
    a = assess("legacy stub call")
    assert a.endurance is not None
    assert a.endurance.point == 0.0
    assert a.thermal_headroom is not None
    assert a.thermal_headroom.point == 0.0


def test_thermal_headroom_drops_when_junction_hot(engine: Engine) -> None:
    baseline = assess("status", engine=engine).thermal_headroom
    assert baseline is not None
    engine.thermal.set_junction_c(80.0)
    for _ in range(40):
        engine.thermal.set_junction_c(80.0)
        engine.tick()
    a = assess("status", engine=engine)
    assert a.thermal_headroom is not None
    assert a.thermal_headroom.point < baseline.point


def test_inference_capacity_falls_to_zero_at_full_load(engine: Engine) -> None:
    engine.compute.set_load_pct(100.0)
    for _ in range(40):
        engine.tick()
    a = assess("burst", engine=engine)
    assert a.inference_capacity is not None
    assert a.inference_capacity.point < 10.0


def test_explain_lists_each_capability(engine: Engine) -> None:
    a = assess("status", engine=engine)
    text = explain(a)
    assert "question" in text
    assert "endurance_min" in text
    assert "thermal_headroom_c" in text
    assert "inference_capacity_tok_per_s" in text


def test_viability_with_explicit_requirements(engine: Engine) -> None:
    a = assess("status", engine=engine)
    feasible = viability(a, "easy task", requirements={"endurance_min": 0.0})
    assert feasible.feasible is True

    unfeasible = viability(
        a,
        "demand-the-impossible",
        requirements={"thermal_headroom_c": 999.0},
    )
    assert unfeasible.feasible is False
    assert "thermal headroom" in unfeasible.reason


def test_viability_keyword_sniffs_endurance(engine: Engine) -> None:
    a = assess("status", engine=engine)
    v = viability(a, "run mission for 5 min")
    assert "endurance" in v.reason or v.feasible


def test_engine_tick_refreshes_last_capabilities(engine: Engine) -> None:
    caps = engine.state.last_capabilities
    assert "endurance_min" in caps
    assert "thermal_headroom_c" in caps
    assert "inference_capacity_tok_per_s" in caps
