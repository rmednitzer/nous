"""Engine integration: position subsystem feeds the EKF and snapshot.

These tests run the real :class:`Engine` and confirm that the BL-010
position subsystem advances ground truth via dead-reckoning, that the
v0.1 :class:`PositionEKF` tracks the truth when a GNSS fix is held,
and that the FSM's safety context can see the fix-lost condition
through `engine.position.has_fix` and the snapshot block.
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


def test_engine_starts_with_fix(engine: Engine) -> None:
    assert engine.position.has_fix is True
    assert engine.position.dead_reckoning_s == pytest.approx(0.0)


def test_dead_reckoning_advances_through_engine_ticks(engine: Engine) -> None:
    engine.position.set_position(45.0, 0.0)
    engine.position.set_velocity(10.0, 0.0)  # 10 m/s north
    start_lat = engine.position.lat
    ticks = 60
    for _ in range(ticks):
        engine.tick()
    expected = start_lat + 10.0 * ticks * engine.dt_s / 111_320.0
    assert engine.position.lat == pytest.approx(expected, abs=1e-6)


def test_position_ekf_tracks_truth_when_fix_held(engine: Engine) -> None:
    engine.position.set_position(45.5, -122.5, alt_m=120.0)
    for _ in range(200):
        engine.tick()
    estimate = engine.position_est.state()
    assert estimate.point["lat"] == pytest.approx(engine.position.lat, abs=1e-4)
    assert estimate.point["lon"] == pytest.approx(engine.position.lon, abs=1e-4)
    assert estimate.point["alt_m"] == pytest.approx(
        engine.position.alt_m, abs=1.0
    )


def test_loss_of_fix_advances_dead_reckoning_counter(engine: Engine) -> None:
    engine.position.set_fix(False)
    for _ in range(30):
        engine.tick()
    assert engine.position.dead_reckoning_s == pytest.approx(
        30 * engine.dt_s, abs=0.01
    )


def test_no_fix_does_not_feed_ekf_observation(engine: Engine) -> None:
    engine.position.set_fix(False)
    before = engine.position_est.state()
    for _ in range(30):
        engine.tick()
    after = engine.position_est.state()
    assert after.covariance["lat"] >= before.covariance["lat"]


def test_snapshot_includes_position_block(engine: Engine) -> None:
    engine.position.set_position(40.0, -120.0)
    engine.tick()
    snap = engine.snapshot()
    assert "position" in snap
    assert snap["position"]["lat"] == pytest.approx(40.0)
    assert snap["position"]["lon"] == pytest.approx(-120.0)
    assert snap["position"]["has_fix"] is True
    assert "dead_reckoning_s" in snap["position"]


def test_engine_starts_position_estimate_at_ground_truth(
    tmp_nous_home: Path,
) -> None:
    eng = Engine()
    estimate = eng.position_est.state()
    truth = eng.position.truth()
    assert estimate.point["lat"] == pytest.approx(truth["lat"], abs=1e-3)
