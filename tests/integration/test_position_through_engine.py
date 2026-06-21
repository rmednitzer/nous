"""Engine integration: position subsystem feeds the EKF and snapshot.

These tests run the real :class:`Engine` and confirm that the BL-010
position subsystem advances ground truth via dead-reckoning, that the
:class:`~nous.estimators.position_ekf.PositionEkf` tracks the truth when a
GNSS fix is held and coasts on the IMU when it is lost (BL-026 / ADR 0073),
and that the FSM's safety context can see the fix-lost condition through
`engine.position.has_fix` and the snapshot block.
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


def test_imu_coast_through_engine_under_gnss_loss(engine: Engine) -> None:
    # Drive north, then lose GNSS: the EKF coasts on the IMU-inferred velocity, so
    # the estimate keeps up with the moving truth far better than a frozen position
    # would (BL-026, the GNSS/INS fusion the whole flagship is about).
    engine.position.set_position(47.0, 13.0, alt_m=500.0)
    engine.position.set_velocity(10.0, 0.0)  # 10 m/s north
    for _ in range(80):
        engine.tick()
    lat_at_loss = engine.position.lat
    engine.position.set_fix(False)
    for _ in range(20):
        engine.tick()
    est_lat = engine.position_est.state().point["lat"]
    truth_lat = engine.position.lat
    assert abs(est_lat - truth_lat) < abs(lat_at_loss - truth_lat)


def test_engine_ekf_estimates_an_injected_imu_accel_bias(engine: Engine) -> None:
    # End to end: a real IMU accelerometer bias, injected as a sensor fault, flows
    # through the engine tick (update(imu) -> predict -> update(gnss)) and the
    # error-state EKF recovers it (ADR 0076). GNSS is held, so the bias cannot hide
    # in position: it is absorbed by the bias state, and position stays locked to
    # truth while `accel_bias_mps2` converges to the injected value.
    engine.imu.set_bias(accel_bias=0.4, freeze_walk=True)
    engine.position.set_position(47.0, 13.0, alt_m=500.0)
    engine.position.set_velocity(10.0, 0.0)  # 10 m/s north, true accel ~ 0
    for _ in range(600):
        engine.position.set_velocity(10.0, 0.0)
        engine.tick()
    est = engine.position_est.state()
    assert est.point["accel_bias_mps2"] == pytest.approx(0.4, abs=0.15)
    # GNSS held: position tracks truth regardless of the absorbed bias.
    assert est.point["lat"] == pytest.approx(engine.position.lat, abs=1e-3)
    assert est.point["lon"] == pytest.approx(engine.position.lon, abs=1e-3)
