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


def test_endurance_band_widens_as_soc_covariance_grows(engine: Engine) -> None:
    """SC-1 / DR-1: a less-certain estimator must yield a wider, less confident
    capability claim, so the controller cannot act on false precision (loss L-1).

    Growing the SoC posterior covariance (predict-only, no observation folded
    in) must widen the endurance band and lower its numeric confidence.
    """
    tight = assess("status", engine=engine).endurance
    assert tight is not None

    for _ in range(50):
        engine.power_est.predict(10.0)

    loose = assess("status", engine=engine).endurance
    assert loose is not None
    assert (loose.p95 - loose.p5) > (tight.p95 - tight.p5)
    assert loose.confidence < tight.confidence


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


def test_viability_fails_closed_when_required_capability_missing() -> None:
    from nous.self_model.assess import Assessment
    from nous.self_model.viability import viability

    bare = Assessment(question="empty")
    v = viability(bare, "demand", requirements={"endurance_min": 5.0})
    assert v.feasible is False
    assert "unavailable" in v.reason


def test_endurance_caps_when_net_charging(engine: Engine) -> None:
    engine.power.set_load_w(0.0)
    engine.apu.set_solar_w(50.0)
    for _ in range(5):
        engine.tick()
    a = assess("charging?", engine=engine)
    assert a.endurance is not None
    assert a.endurance.point <= 24 * 60.0 + 1.0


def test_engine_tick_refreshes_last_capabilities(engine: Engine) -> None:
    caps = engine.state.last_capabilities
    assert "endurance_min" in caps
    assert "thermal_headroom_c" in caps
    assert "inference_capacity_tok_per_s" in caps


def test_monte_carlo_and_gaussian_modes_agree_on_point(engine: Engine) -> None:
    """The headline point is mode-invariant; only the bands shift between MC and Gaussian."""
    mc = assess("status", engine=engine, mode="monte_carlo")
    gauss = assess("status", engine=engine, mode="gaussian")
    assert mc.endurance is not None and gauss.endurance is not None
    assert mc.endurance.point == pytest.approx(gauss.endurance.point)
    assert mc.thermal_headroom is not None and gauss.thermal_headroom is not None
    assert mc.thermal_headroom.point == pytest.approx(gauss.thermal_headroom.point)


def test_assess_is_deterministic_under_seed(engine: Engine) -> None:
    """Two calls with the same seed produce identical quantile bands."""
    a = assess("status", engine=engine, seed=99)
    b = assess("status", engine=engine, seed=99)
    assert a.endurance is not None and b.endurance is not None
    assert a.endurance.p5 == pytest.approx(b.endurance.p5)
    assert a.endurance.p95 == pytest.approx(b.endurance.p95)


def test_monte_carlo_quantiles_respect_endurance_floor(engine: Engine) -> None:
    """Sampled SoC at 0 should not produce negative endurance quantiles."""
    engine.power.set_soc_pct(10.0)
    for _ in range(5):
        engine.tick()
    a = assess("low soc", engine=engine, mode="monte_carlo")
    assert a.endurance is not None
    assert a.endurance.p5 >= 0.0
