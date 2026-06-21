"""Unit tests for the BL-026 IMU subsystem."""

from __future__ import annotations

import math

import numpy as np
import pytest

from nous.subsystems.imu import ImuSubsystem


def test_constant_velocity_has_zero_accel_and_yaw_rate() -> None:
    imu = ImuSubsystem({})
    imu.set_motion(10.0, 90.0)
    imu.step(0.5)
    imu.set_motion(10.0, 90.0)
    imu.step(0.5)
    assert imu.accel_mps2 == pytest.approx(0.0, abs=1e-9)
    assert imu.yaw_rate_rps == pytest.approx(0.0, abs=1e-9)


def test_acceleration_is_speed_derivative() -> None:
    imu = ImuSubsystem({})
    imu.set_motion(0.0, 0.0)
    imu.step(1.0)
    imu.set_motion(5.0, 0.0)
    imu.step(1.0)
    assert imu.accel_mps2 == pytest.approx(5.0)


def test_yaw_rate_is_heading_derivative() -> None:
    imu = ImuSubsystem({})
    imu.set_motion(1.0, 0.0)
    imu.step(1.0)
    imu.set_motion(1.0, 10.0)
    imu.step(1.0)
    assert imu.yaw_rate_rps == pytest.approx(math.radians(10.0))


def test_yaw_rate_takes_the_short_arc() -> None:
    imu = ImuSubsystem({})
    imu.set_motion(1.0, 350.0)
    imu.step(1.0)
    imu.set_motion(1.0, 10.0)  # 350 -> 10 is +20 deg, not -340
    imu.step(1.0)
    assert imu.yaw_rate_rps == pytest.approx(math.radians(20.0))


def test_obs_is_truth_without_rng() -> None:
    imu = ImuSubsystem({})  # no rng: no bias walk, no noise
    imu.set_motion(0.0, 0.0)
    imu.step(1.0)
    imu.set_motion(4.0, 0.0)
    imu.step(1.0)
    obs = imu.sensor_obs()
    assert obs.source == "imu"
    assert obs.payload["accel_mps2"] == pytest.approx(4.0)
    assert obs.payload["yaw_rate_rps"] == pytest.approx(0.0)


def test_bias_walks_deterministically_under_seed() -> None:
    a = ImuSubsystem({}, rng=np.random.default_rng(7))
    b = ImuSubsystem({}, rng=np.random.default_rng(7))
    for _ in range(20):
        a.set_motion(5.0, 45.0)
        a.step(0.5)
        b.set_motion(5.0, 45.0)
        b.step(0.5)
    assert a.accel_bias == b.accel_bias
    assert a.gyro_bias == b.gyro_bias


def test_set_bias_injects_a_known_bias_into_the_observation() -> None:
    imu = ImuSubsystem({})  # no rng: the obs is truth + the injected bias
    imu.set_bias(accel_bias=0.4, gyro_bias=-0.02)
    imu.set_motion(0.0, 0.0)
    imu.step(1.0)
    imu.set_motion(3.0, 0.0)
    imu.step(1.0)
    obs = imu.sensor_obs()
    assert imu.accel_bias == pytest.approx(0.4)
    assert imu.gyro_bias == pytest.approx(-0.02)
    assert obs.payload["accel_mps2"] == pytest.approx(3.0 + 0.4)
    assert obs.payload["yaw_rate_rps"] == pytest.approx(-0.02)


def test_freeze_walk_pins_an_injected_bias_under_stepping() -> None:
    imu = ImuSubsystem({}, rng=np.random.default_rng(3))
    imu.set_bias(accel_bias=0.5, gyro_bias=0.01, freeze_walk=True)
    for _ in range(50):
        imu.set_motion(8.0, 30.0)
        imu.step(0.5)
    # The walk is frozen, so the bias is exactly what was injected.
    assert imu.accel_bias == pytest.approx(0.5)
    assert imu.gyro_bias == pytest.approx(0.01)
