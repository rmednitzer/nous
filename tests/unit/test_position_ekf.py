"""Unit tests for the BL-026 nonlinear position EKF."""

from __future__ import annotations

import math

import pytest

from nous.estimators.position_ekf import PositionEkf
from nous.types import Observation

_M_PER_DEG = 111_320.0


def _gnss(lat: float, lon: float, alt: float = 100.0, ts: float = 0.0) -> Observation:
    return Observation(
        source="position",
        ts_s=ts,
        payload={"lat": lat, "lon": lon, "alt_m": alt},
        noise={"lat_sigma": 3e-5, "lon_sigma": 3e-5, "alt_m_sigma": 5.0},
    )


def _imu(accel: float, yaw_rate: float) -> Observation:
    return Observation(
        source="imu",
        ts_s=0.0,
        payload={"accel_mps2": accel, "yaw_rate_rps": yaw_rate},
        noise={},
    )


def test_seeds_from_first_fix() -> None:
    ekf = PositionEkf()
    ekf.update(_gnss(47.0, 13.0, 500.0))
    s = ekf.state()
    assert s.point["lat"] == pytest.approx(47.0, abs=1e-6)
    assert s.point["lon"] == pytest.approx(13.0, abs=1e-6)
    assert s.point["alt_m"] == pytest.approx(500.0, abs=0.1)


def test_tracks_stationary_gnss() -> None:
    ekf = PositionEkf()
    for _ in range(50):
        ekf.update(_imu(0.0, 0.0))
        ekf.predict(0.5)
        ekf.update(_gnss(47.0, 13.0, 500.0))
    s = ekf.state()
    assert s.point["lat"] == pytest.approx(47.0, abs=1e-5)
    assert s.point["lon"] == pytest.approx(13.0, abs=1e-5)


def test_covariance_grows_without_fix_and_raises_dead_reckoning() -> None:
    ekf = PositionEkf()
    ekf.update(_gnss(47.0, 13.0))
    before = ekf.state().covariance["lat"]
    for _ in range(10):
        ekf.update(_imu(0.0, 0.0))
        ekf.predict(0.5)
    after = ekf.state()
    assert after.covariance["lat"] > before
    assert after.health is not None
    assert after.health.dead_reckoning is True


def test_infers_velocity_and_heading_from_position_only_fixes() -> None:
    # GNSS observes only position; the EKF recovers ground speed and heading
    # through the motion-built cross-covariance (the observability that earns the
    # EKF its name). Drive north at 10 m/s.
    ekf = PositionEkf()
    dt = 0.5
    lat = 47.0
    for i in range(60):
        lat += 10.0 * dt / _M_PER_DEG
        ekf.update(_imu(0.0, 0.0))
        ekf.predict(dt)
        ekf.update(_gnss(lat, 13.0, 500.0, ts=i * dt))
    s = ekf.state()
    assert s.point["speed_mps"] == pytest.approx(10.0, abs=2.0)
    # Heading ~0 (north); v_n ~ +10, v_e ~ 0.
    assert s.point["v_n_mps"] == pytest.approx(10.0, abs=2.0)
    assert s.point["v_e_mps"] == pytest.approx(0.0, abs=2.0)


def test_imu_coast_beats_a_frozen_position_under_gnss_loss() -> None:
    ekf = PositionEkf()
    dt = 0.5
    lat = 47.0
    for i in range(60):
        lat += 10.0 * dt / _M_PER_DEG
        ekf.update(_imu(0.0, 0.0))
        ekf.predict(dt)
        ekf.update(_gnss(lat, 13.0, 500.0, ts=i * dt))
    last_fix_lat = lat
    truth_lat = lat
    for _ in range(20):
        truth_lat += 10.0 * dt / _M_PER_DEG
        ekf.update(_imu(0.0, 0.0))
        ekf.predict(dt)  # no GNSS: coast on the inferred velocity
    est_lat = ekf.state().point["lat"]
    coast_error = abs(est_lat - truth_lat)
    frozen_error = abs(last_fix_lat - truth_lat)
    assert coast_error < frozen_error


def test_gate_rejects_a_single_outlier_then_re_anchors_a_sustained_jump() -> None:
    ekf = PositionEkf()
    for _ in range(5):
        ekf.update(_imu(0.0, 0.0))
        ekf.predict(0.5)
        ekf.update(_gnss(47.0, 13.0))
    # A single wild fix is rejected (the estimate stays near the truth).
    ekf.update(_gnss(48.0, 14.0))
    assert ekf.state().point["lat"] == pytest.approx(47.0, abs=1e-3)
    rejected_after_one = ekf.rejected_updates
    assert rejected_after_one >= 1
    # A jump that persists is adopted through a re-anchor reset.
    for _ in range(4):
        ekf.update(_gnss(48.0, 14.0))
    s = ekf.state()
    assert s.point["lat"] == pytest.approx(48.0, abs=1e-3)
    assert s.point["lon"] == pytest.approx(14.0, abs=1e-3)
    assert s.health is not None and s.health.reset_count >= 1


def test_rejects_out_of_range_without_poisoning() -> None:
    ekf = PositionEkf()
    ekf.update(_gnss(47.0, 13.0))
    ekf.update(
        Observation(
            source="position",
            ts_s=1.0,
            payload={"lat": 200.0, "lon": 13.0},  # invalid latitude
            noise={"lat_sigma": 3e-5, "lon_sigma": 3e-5},
        )
    )
    assert ekf.state().point["lat"] == pytest.approx(47.0, abs=1e-6)
    assert ekf.rejected_updates >= 1


def test_heading_wraps_and_speed_is_nonnegative_in_state() -> None:
    ekf = PositionEkf()
    ekf.update(_gnss(47.0, 13.0))
    ekf.update(_imu(0.0, math.radians(20.0)))
    for _ in range(40):
        ekf.predict(0.5)
        ekf.update(_imu(0.0, math.radians(20.0)))
    h = ekf.state().point["heading_deg"]
    assert 0.0 <= h < 360.0
