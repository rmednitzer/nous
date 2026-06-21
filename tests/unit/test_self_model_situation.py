"""Unit tests for the BL-061 self-model situational-awareness layer (ADR 0038)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine
from nous.self_model.assess import assess
from nous.self_model.situation import Situation, situation
from nous.state.comms_state import CommsState
from nous.state.machine import Mode
from nous.state.operator_state import OperatorState

_CAP_NAMES = {
    "endurance_min",
    "thermal_headroom_c",
    "inference_capacity_tok_per_s",
    "perception_range_m",
}
_STATUSES = {"nominal", "watch", "degraded", "critical"}


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()  # start() lands in IDLE (ADR 0039)
    eng.tick()
    return eng


def test_situation_fuses_capabilities_with_provenance(engine: Engine) -> None:
    s = situation(engine)
    assert isinstance(s, Situation)
    assert {c.name for c in s.capabilities} >= _CAP_NAMES
    for cap in s.capabilities:
        assert cap.p5 <= cap.p50 <= cap.p95
        assert cap.status in _STATUSES
        assert cap.provenance, f"{cap.name} should name where it comes from"
        for prov in cap.provenance:
            assert prov.source
            assert prov.age_s >= 0.0


def test_headline_numbers_match_assess(engine: Engine) -> None:
    """situation reuses assess, so the point and band figures are identical."""
    a = assess("situation", engine=engine, seed=0)
    s = situation(engine, seed=0)
    by_name = {c.name: c for c in s.capabilities}
    assert a.endurance is not None
    assert by_name["endurance_min"].point == pytest.approx(a.endurance.point)
    assert by_name["endurance_min"].p5 == pytest.approx(a.endurance.p5)
    assert by_name["endurance_min"].p95 == pytest.approx(a.endurance.p95)


def test_provenance_age_is_zero_under_live_ticking(engine: Engine) -> None:
    """Every estimator updates each tick, so a freshly ticked estimate is current."""
    engine.tick()
    s = situation(engine)
    ages = [p.age_s for c in s.capabilities for p in c.provenance]
    assert ages
    assert max(ages) == pytest.approx(0.0, abs=1e-6)


def test_provenance_age_survives_profile_reload(engine: Engine) -> None:
    """profile_reload rebuilds estimators on a fresh timebase while preserving the
    engine clock; staleness must stay measured against the estimator clock so it
    reads ~0 rather than jumping to the pre-reload elapsed time."""
    for _ in range(5):
        engine.tick()
    engine.reload_profile()
    s = situation(engine)
    ages = [p.age_s for c in s.capabilities for p in c.provenance]
    assert ages
    assert max(ages) == pytest.approx(0.0, abs=1e-6)


def test_posture_reports_mode_and_labels(engine: Engine) -> None:
    s = situation(engine)
    assert s.posture.mode == engine.state.mode.value
    assert s.posture.operator_state == engine.state.operator_state.value
    assert s.posture.comms_state == engine.state.comms_state.value
    assert s.posture.summary in {"nominal", "degraded", "safed", "terminal", "standby"}


def test_nominal_engine_recommends_no_action(engine: Engine) -> None:
    """A freshly booted reference engine is healthy: the fallback line stands."""
    s = situation(engine)
    assert any("no action required" in r for r in s.recommendations)


def test_safety_posture_is_surfaced(engine: Engine) -> None:
    s = situation(engine)
    assert "total_violations" in s.safety
    assert "registered" in s.safety


def test_thermal_throttling_drives_status_and_recommendation(engine: Engine) -> None:
    # Force the junction over the throttle threshold and read without ticking, so
    # `throttling` (junction_c >= threshold) holds rather than relaxing under the
    # integrator. This is the live "thermally limited now" signal situation keys
    # the status on.
    engine.thermal.set_junction_c(90.0)
    s = situation(engine)
    thermal = next(c for c in s.capabilities if c.name == "thermal_headroom_c")
    assert thermal.status == "critical"
    assert any(r.startswith("thermal:") for r in s.recommendations)
    assert s.posture.summary in {"degraded", "safed"}


def test_fog_and_night_drive_perception_status_and_recommendation(engine: Engine) -> None:
    engine.eoir.set_obscurant(1.0)
    engine.eoir.set_illumination(0.05)
    for _ in range(20):
        engine.tick()
    s = situation(engine)
    perception = next(c for c in s.capabilities if c.name == "perception_range_m")
    assert perception.status in {"degraded", "critical"}
    assert {p.source for p in perception.provenance} >= {"eoir", "sensors"}
    rec = next(r for r in s.recommendations if r.startswith("perception:"))
    # Best band under heavy fog is the infrared one, limited by obscuration.
    assert "atmospheric obscuration" in rec


def test_full_load_drives_inference_status_critical(engine: Engine) -> None:
    engine.compute.set_load_pct(100.0)
    for _ in range(40):
        engine.tick()
    s = situation(engine)
    inference = next(
        c for c in s.capabilities if c.name == "inference_capacity_tok_per_s"
    )
    assert inference.status == "critical"
    assert any(r.startswith("inference:") for r in s.recommendations)


def test_mode_throttle_drives_inference_degraded_with_advisory(engine: Engine) -> None:
    # A mode-load ceiling (not thermal) clips delivered load below the request, so
    # compute.throttled is true while inference capacity stays above the floor: the
    # inference status is degraded, and ADR 0071 gives it its own advisory even
    # though no thermal advisory fires.
    for _ in range(6):
        engine.compute.set_mode_load_ceiling(50.0)
        engine.compute.set_load_pct(100.0)
        engine.tick()
    s = situation(engine)
    inference = next(
        c for c in s.capabilities if c.name == "inference_capacity_tok_per_s"
    )
    assert inference.status == "degraded"
    assert engine.compute.throttled is True
    assert any(r.startswith("inference:") for r in s.recommendations)
    assert not any(r.startswith("thermal:") for r in s.recommendations)


def test_operator_incapacitated_recommends_safe_hold(engine: Engine) -> None:
    engine.state.operator_state = OperatorState.INCAPACITATED
    engine.state.operator_state_reason = "no vitals detected"
    s = situation(engine)
    assert any(r.startswith("operator:") for r in s.recommendations)
    assert s.posture.summary == "degraded"


def test_comms_denied_in_link_mode_recommends_link_action(engine: Engine) -> None:
    engine.state.mode = Mode.RELAY
    engine.state.comms_state = CommsState.DENIED
    engine.state.comms_state_reason = "all links timed out"
    s = situation(engine)
    assert any("relay/c2" in r for r in s.recommendations)
    assert s.posture.summary == "degraded"


def test_lost_fix_recommends_navigation_caution(engine: Engine) -> None:
    engine.position.set_fix(False)
    engine.tick()
    s = situation(engine)
    assert any(r.startswith("navigation:") for r in s.recommendations)


def test_situation_is_deterministic_under_seed(engine: Engine) -> None:
    a = situation(engine, seed=7)
    b = situation(engine, seed=7)
    assert a.model_dump() == b.model_dump()
