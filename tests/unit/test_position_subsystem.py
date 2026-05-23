"""Position subsystem: dead reckoning, fix gating, profile noise wiring."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.position import PositionSubsystem


def _profile(**overrides: Any) -> Mapping[str, Any]:
    base: dict[str, Any] = {
        "lat_sigma": 3.0e-5,
        "lon_sigma": 3.0e-5,
        "alt_m_sigma": 5.0,
        "fix_rate_hz": 10.0,
    }
    base.update(overrides)
    return {"sensors": {"position": base}}


def test_starts_at_default_position() -> None:
    p = PositionSubsystem(_profile())
    assert p.lat == pytest.approx(47.0)
    assert p.lon == pytest.approx(13.0)
    assert p.alt_m == pytest.approx(500.0)
    assert p.has_fix is True


def test_set_position_teleports_ground_truth() -> None:
    p = PositionSubsystem(_profile())
    p.set_position(48.5, -122.5, alt_m=120.0)
    assert p.lat == pytest.approx(48.5)
    assert p.lon == pytest.approx(-122.5)
    assert p.alt_m == pytest.approx(120.0)


def test_set_position_clamps_latitude_and_wraps_longitude() -> None:
    p = PositionSubsystem(_profile())
    p.set_position(95.0, 200.0)
    assert p.lat == pytest.approx(90.0)
    assert p.lon == pytest.approx(-160.0)  # 200 wrapped


def test_set_velocity_clamps_negative_speed_and_normalises_heading() -> None:
    p = PositionSubsystem(_profile())
    p.set_velocity(-3.0, 720.0)
    assert p.speed_mps == pytest.approx(0.0)
    assert p.heading_deg == pytest.approx(0.0)


def test_dead_reckoning_north_moves_latitude_positive() -> None:
    p = PositionSubsystem(_profile())
    p.set_position(45.0, 0.0)
    p.set_velocity(10.0, 0.0)  # 10 m/s north
    p.step(60.0)
    expected_dlat = 10.0 * 60.0 / 111_320.0
    assert p.lat == pytest.approx(45.0 + expected_dlat, abs=1e-6)
    assert p.lon == pytest.approx(0.0, abs=1e-9)


def test_dead_reckoning_east_moves_longitude_positive() -> None:
    p = PositionSubsystem(_profile())
    p.set_position(45.0, 0.0)
    p.set_velocity(10.0, 90.0)  # 10 m/s east
    p.step(60.0)
    cos_lat = math.cos(math.radians(45.0))
    expected_dlon = 10.0 * 60.0 / (111_320.0 * cos_lat)
    assert p.lon == pytest.approx(expected_dlon, abs=1e-6)
    assert p.lat == pytest.approx(45.0, abs=1e-9)


def test_vertical_velocity_changes_altitude() -> None:
    p = PositionSubsystem(_profile())
    p.set_velocity(0.0, 0.0, vertical_mps=2.0)
    p.step(10.0)
    assert p.alt_m == pytest.approx(520.0)


def test_no_fix_makes_observation_payload_empty() -> None:
    p = PositionSubsystem(_profile())
    p.set_fix(False)
    obs = p.sensor_obs()
    assert obs.payload == {}
    assert obs.noise == {}


def test_fix_restored_repopulates_observation() -> None:
    p = PositionSubsystem(_profile())
    p.set_fix(False)
    p.set_fix(True)
    obs = p.sensor_obs()
    assert "lat" in obs.payload
    assert obs.noise["lat_sigma"] > 0.0


def test_dead_reckoning_counter_advances_only_when_fix_lost() -> None:
    p = PositionSubsystem(_profile())
    p.step(5.0)
    assert p.dead_reckoning_s == pytest.approx(0.0)
    p.set_fix(False)
    p.step(7.0)
    assert p.dead_reckoning_s == pytest.approx(7.0)


def test_fix_reset_clears_dead_reckoning_counter() -> None:
    p = PositionSubsystem(_profile())
    p.set_fix(False)
    p.step(10.0)
    p.set_fix(True)
    assert p.dead_reckoning_s == pytest.approx(0.0)


def test_imu_drift_only_applied_without_fix() -> None:
    p = PositionSubsystem(_profile())
    p.set_position(0.0, 0.0)
    p.set_imu_drift(north_mps=1.0, east_mps=0.0)
    p.step(60.0)
    # With fix: drift ignored
    assert p.lat == pytest.approx(0.0, abs=1e-9)

    p.set_fix(False)
    p.step(60.0)
    expected_dlat = 1.0 * 60.0 / 111_320.0
    assert p.lat == pytest.approx(expected_dlat, abs=1e-6)


def test_profile_sigmas_appear_in_observation_noise() -> None:
    p = PositionSubsystem(_profile(lat_sigma=5e-5, lon_sigma=5e-5, alt_m_sigma=10.0))
    obs = p.sensor_obs()
    assert obs.noise["lat_sigma"] == pytest.approx(5e-5)
    assert obs.noise["lon_sigma"] == pytest.approx(5e-5)
    assert obs.noise["alt_m_sigma"] == pytest.approx(10.0)


def test_defaults_when_position_section_missing() -> None:
    p = PositionSubsystem({})
    assert p.lat == pytest.approx(47.0)
    assert p.has_fix is True
    assert p.fix_rate_hz == pytest.approx(10.0)


def test_longitude_wraps_through_antimeridian() -> None:
    p = PositionSubsystem(_profile())
    p.set_position(0.0, 179.99)
    p.set_velocity(1000.0, 90.0)  # blast east
    p.step(60.0)
    assert -180.0 <= p.lon <= 180.0


def test_zero_step_is_noop() -> None:
    p = PositionSubsystem(_profile())
    p.set_velocity(10.0, 90.0)
    before = (p.lat, p.lon)
    p.step(0.0)
    p.step(-1.0)
    assert (p.lat, p.lon) == before
