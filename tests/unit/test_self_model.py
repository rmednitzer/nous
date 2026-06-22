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
    assert a.perception_range is not None

    assert a.endurance.units == "min"
    assert a.thermal_headroom.units == "C"
    assert a.inference_capacity.units == "tok/s"
    assert a.perception_range.units == "m"
    assert a.perception_range.name == "perception_range_m"

    for cap in (
        a.endurance,
        a.thermal_headroom,
        a.inference_capacity,
        a.perception_range,
    ):
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


def test_perception_range_is_the_best_band(engine: Engine) -> None:
    a = assess("how far can i see?", engine=engine)
    assert a.perception_range is not None
    best = max(engine.eoir.eo_range_m, engine.eoir.ir_range_m)
    assert a.perception_range.point == pytest.approx(best, rel=0.05)
    assert a.perception_range.drivers == ["eoir", "sensors"]


def test_perception_range_collapses_under_fog_and_night(engine: Engine) -> None:
    baseline = assess("see", engine=engine).perception_range
    assert baseline is not None
    engine.eoir.set_obscurant(1.0)
    engine.eoir.set_illumination(0.05)
    for _ in range(20):
        engine.tick()
    degraded = assess("see", engine=engine).perception_range
    assert degraded is not None
    assert degraded.point < baseline.point


def test_explain_lists_each_capability(engine: Engine) -> None:
    a = assess("status", engine=engine)
    text = explain(a)
    assert "question" in text
    assert "endurance_min" in text
    assert "thermal_headroom_c" in text
    assert "inference_capacity_tok_per_s" in text
    assert "perception_range_m" in text


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
    # Below the PMU's CV knee the charge is not tapered (BL-005b / ADR 0075), so a
    # generous source net-charges a light idle load and the endurance is a capped
    # hint rather than an unbounded figure.
    engine.power.set_soc_pct(50.0)
    engine.compute.set_load_pct(0.0)
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
    assert "perception_range_m" in caps


def test_tick_refresh_matches_monte_carlo_points(engine: Engine) -> None:
    """The Gaussian fast path on the tick loop (BL-073) yields the same headline
    points a full Monte Carlo ``assess`` would, so the cheaper refresh leaves
    ``state.last_capabilities`` identical to the calibrated tool-facing read."""
    caps = engine.state.last_capabilities
    mc = assess("tick", engine=engine, mode="monte_carlo")
    for cap in (mc.endurance, mc.thermal_headroom, mc.inference_capacity, mc.perception_range):
        assert cap is not None
        # Strict equality, not approx: point is computed deterministically before
        # the mode branch, so the Gaussian refresh and a Monte Carlo read must
        # produce the identical float -- the whole premise of the fast path.
        assert caps[cap.name] == cap.point


def test_viability_gates_on_perception_range(engine: Engine) -> None:
    a = assess("detect a target", engine=engine)
    reachable = viability(a, "detect", requirements={"perception_range_m": 1000.0})
    assert reachable.feasible is True
    beyond = viability(a, "detect", requirements={"perception_range_m": 50000.0})
    assert beyond.feasible is False
    assert "perception range" in beyond.reason


def test_monte_carlo_and_gaussian_modes_agree_on_point(engine: Engine) -> None:
    """The headline point is mode-invariant; only the bands shift between MC and Gaussian.

    The tick-loop capability refresh relies on this: it reads only each claim's
    ``point`` and calls ``assess`` in the cheaper Gaussian mode (BL-073), so a
    drift between the two modes' points would silently change
    ``state.last_capabilities``. Pin all four claims, not just two.
    """
    mc = assess("status", engine=engine, mode="monte_carlo")
    gauss = assess("status", engine=engine, mode="gaussian")
    for name in ("endurance", "thermal_headroom", "inference_capacity", "perception_range"):
        mc_cap = getattr(mc, name)
        gauss_cap = getattr(gauss, name)
        assert mc_cap is not None and gauss_cap is not None
        # Strict equality: point is rng-independent and computed before the mode
        # branch, so any drift between modes is a real regression the fast path
        # must not tolerate, not a tolerable numeric wobble.
        assert mc_cap.point == gauss_cap.point, name


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


def test_monte_carlo_p50_is_the_sample_median_not_the_point(engine: Engine) -> None:
    """ASSESS-1: the Monte Carlo band's p50 is the empirical sample median, so
    the centre and the tails come from one sample. The old behaviour pinned
    p50 to the deterministic point exactly; the sample median of a
    non-degenerate posterior does not equal that point, while the Gaussian
    fallback (median == mean) still reports the point."""
    for _ in range(4):
        engine.tick()

    mc = assess("status", engine=engine, mode="monte_carlo", seed=7)
    assert mc.thermal_headroom is not None
    cap = mc.thermal_headroom
    # The thermal posterior has spread, so the Monte Carlo branch runs.
    assert cap.p5 < cap.p95
    assert cap.p5 <= cap.p50 <= cap.p95
    # The centre is the sample median, not the deterministic point.
    assert cap.p50 != cap.point

    gauss = assess("status", engine=engine, mode="gaussian", seed=7)
    assert gauss.thermal_headroom is not None
    assert gauss.thermal_headroom.p50 == pytest.approx(gauss.thermal_headroom.point)


def test_thermal_headroom_band_includes_throttle_prior(engine: Engine) -> None:
    """ADR 0080: the throttle-threshold design prior widens the headroom band
    past the junction posterior alone, so the band stops treating the datasheet
    threshold as exact. Same seed isolates the prior as the only difference."""
    with_prior = assess("status", engine=engine, seed=11).thermal_headroom
    engine.profile = {
        **engine.profile,
        "self_model": {"priors": {"junction_throttle_sigma_c": 0.0}},
    }
    without_prior = assess("status", engine=engine, seed=11).thermal_headroom
    assert with_prior is not None and without_prior is not None
    assert (with_prior.p95 - with_prior.p5) > (without_prior.p95 - without_prior.p5)


def test_inference_capacity_band_includes_token_rate_prior(engine: Engine) -> None:
    """ADR 0080: the benchmark token-rate design prior widens the capacity band
    past the load posterior alone."""
    with_prior = assess("status", engine=engine, seed=11).inference_capacity
    engine.profile = {
        **engine.profile,
        "self_model": {"priors": {"tok_per_s_cv": 0.0}},
    }
    without_prior = assess("status", engine=engine, seed=11).inference_capacity
    assert with_prior is not None and without_prior is not None
    assert (with_prior.p95 - with_prior.p5) > (without_prior.p95 - without_prior.p5)


def test_endurance_net_load_propagation_is_default_and_disablable(engine: Engine) -> None:
    """ADR 0082: net-load propagation (the APU-charge and compute-draw posteriors
    through net load) is on by default, so the endurance band reflects net-load
    uncertainty and names the extra drivers. Disabling it narrows the band to the
    SoC and battery posteriors alone."""
    default = assess("status", engine=engine, seed=5).endurance
    engine.profile = {
        **engine.profile,
        "self_model": {"priors": {"propagate_net_load": False}},
    }
    disabled = assess("status", engine=engine, seed=5).endurance
    assert default is not None and disabled is not None
    assert default.drivers == ["power", "apu"]
    assert disabled.drivers == ["power"]
    assert (default.p95 - default.p5) > (disabled.p95 - disabled.p5)
    assert default.p5 >= 0.0


def test_priors_coerce_junk_profile_values_to_defaults(engine: Engine) -> None:
    """Profile content is attacker-influenceable; a non-numeric prior falls back
    to its default rather than poisoning a band, so the junk band equals the
    default-prior band under the same seed."""
    clean = assess("status", engine=engine, seed=3).thermal_headroom
    engine.profile = {
        **engine.profile,
        "self_model": {"priors": {"junction_throttle_sigma_c": "boom"}},
    }
    junk = assess("status", engine=engine, seed=3).thermal_headroom
    assert clean is not None and junk is not None
    assert junk.p5 == pytest.approx(clean.p5)
    assert junk.p95 == pytest.approx(clean.p95)


def test_priors_reject_bool_cv_and_coerce_flag(engine: Engine) -> None:
    """Defensive coercion (ADR 0082): a bool is not a valid prior spread
    (`float(True)` is `1.0`), so it falls back to the default spread. The
    propagate_net_load flag honours a real boolean (`False` disables) and falls
    back to the default (on) for a non-bool, so a typo widens the band rather
    than silently disabling it."""
    clean = assess("status", engine=engine, seed=3).inference_capacity
    # A bool tok_per_s_cv is not a valid spread (float(True) == 1.0); it falls
    # back to the default, leaving the inference band unchanged. propagate_net_load
    # is left at its default so endurance draws the rng stream identically.
    engine.profile = {**engine.profile, "self_model": {"priors": {"tok_per_s_cv": True}}}
    a = assess("status", engine=engine, seed=3).inference_capacity
    assert a is not None and clean is not None
    assert a.p95 == pytest.approx(clean.p95)

    # A real bool False disables propagation; a non-bool (e.g. a quoted "false")
    # is junk and falls back to the default (on), so a typo widens the band
    # rather than silently disabling it.
    engine.profile = {**engine.profile, "self_model": {"priors": {"propagate_net_load": False}}}
    disabled = assess("status", engine=engine, seed=3).endurance
    assert disabled is not None and disabled.drivers == ["power"]

    engine.profile = {
        **engine.profile,
        "self_model": {"priors": {"propagate_net_load": "false"}},
    }
    junk = assess("status", engine=engine, seed=3).endurance
    assert junk is not None and junk.drivers == ["power", "apu"]


def test_endurance_negative_battery_wh_does_not_raise(engine: Engine) -> None:
    """A negative injected `battery_wh` must not raise from numpy's scale
    argument; the sampling sigma is clamped non-negative (ADR 0080)."""
    engine.power.profile["power"]["battery_wh"] = -10.0
    a = assess("status", engine=engine)
    assert a.endurance is not None
