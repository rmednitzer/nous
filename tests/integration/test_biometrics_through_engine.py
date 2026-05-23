"""Engine integration: biometrics subsystem through the tick loop.

The biometrics subsystem is the controller's window into operator
state. These tests run the real :class:`Engine` and confirm that
scenario seams set the ground truth, the Kalman estimator tracks
truth across ticks (including the newly tracked hydration channel),
and the snapshot block exposes the four scalars the FSM and
self-model layer key off.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    return eng


def test_engine_starts_at_nominal_biometrics(engine: Engine) -> None:
    assert engine.biometrics.heart_rate_bpm == pytest.approx(70.0)
    assert engine.biometrics.core_temp_c == pytest.approx(37.0)
    assert engine.biometrics.hydration_pct == pytest.approx(90.0)
    assert engine.biometrics.cognitive_load == pytest.approx(0.2)


def test_set_heart_rate_propagates_through_estimator(engine: Engine) -> None:
    engine.biometrics.set_heart_rate_bpm(150.0)
    for _ in range(60):
        engine.tick()
    estimate = engine.biometrics_est.state()
    assert estimate.point["heart_rate_bpm"] == pytest.approx(150.0, abs=2.0)


def test_hydration_drop_propagates_through_estimator(engine: Engine) -> None:
    engine.biometrics.set_hydration_pct(60.0)
    for _ in range(60):
        engine.tick()
    estimate = engine.biometrics_est.state()
    assert estimate.point["hydration_pct"] == pytest.approx(60.0, abs=2.0)


def test_estimator_validates_out_of_envelope_subsystem_writes(engine: Engine) -> None:
    """The subsystem clamps, so even a `set_core_temp_c(60)` lands at 44 C and
    the estimator's bounds check accepts the clamped value."""
    engine.biometrics.set_core_temp_c(60.0)
    assert engine.biometrics.core_temp_c == pytest.approx(44.0)
    for _ in range(20):
        engine.tick()
    estimate = engine.biometrics_est.state()
    assert estimate.point["core_temp_c"] == pytest.approx(44.0, abs=0.5)
    assert engine.biometrics_est.rejected_updates == 0


def test_snapshot_includes_biometrics_block(engine: Engine) -> None:
    engine.biometrics.set_heart_rate_bpm(110.0)
    engine.biometrics.set_cognitive_load(0.6)
    engine.tick()
    snap = engine.snapshot()
    assert "biometrics" in snap
    assert snap["biometrics"]["heart_rate_bpm"] == pytest.approx(110.0)
    assert snap["biometrics"]["cognitive_load"] == pytest.approx(0.6)
    assert "hydration_pct" in snap["biometrics"]
    assert "core_temp_c" in snap["biometrics"]


def test_engine_seeds_estimator_from_subsystem_truth(tmp_nous_home: Path) -> None:
    """The initial seed-update pulls the prior (70 bpm) toward truth; a few
    ticks of `predict + update` then converge to the new ground truth."""
    profile = {
        "sensors": {
            "biometrics": {
                "heart_rate_bpm_default": 95.0,
                "heart_rate_bpm_sigma": 2.0,
            }
        }
    }
    eng = Engine(profile=profile)
    eng.start()
    for _ in range(30):
        eng.tick()
    estimate = eng.biometrics_est.state()
    assert estimate.point["heart_rate_bpm"] == pytest.approx(95.0, abs=2.0)
