"""APU subsystem: per-source physics and composition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.apu import ApuSubsystem


def _profile(**overrides: Any) -> Mapping[str, Any]:
    base: dict[str, Any] = {
        "solar": {
            "panel_w_peak": 60.0,
            "mppt_efficiency": 0.9,
            "panel_temp_derate_per_c_above_25": 0.01,
        },
        "fuel_cell": {
            "continuous_w": 25.0,
            "fuel_capacity_g": 100.0,
            "efficiency": 0.45,
            "wh_per_g_fuel": 2.5,
        },
        "vehicle": {
            "bus_voltage_v": 28.0,
            "current_limit_a": 5.0,
        },
        "usb_c_pd": {
            "profiles_w": [15.0, 27.0, 45.0, 60.0],
            "default_profile_w": 60.0,
        },
    }
    base.update(overrides)
    return {"apu": base}


def test_starts_idle_all_sources_zero() -> None:
    apu = ApuSubsystem(_profile())
    apu.step(1.0)
    truth = apu.truth()
    assert truth["solar_w"] == 0.0
    assert truth["fuelcell_w"] == 0.0
    assert truth["vehicle_w"] == 0.0
    assert truth["usbc_w"] == 0.0
    assert truth["total_w"] == 0.0


def test_solar_direct_override() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_solar_w(40.0)
    apu.step(1.0)
    assert apu.truth()["solar_w"] == pytest.approx(40.0)


def test_solar_override_clamped_to_peak() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_solar_w(500.0)
    apu.step(1.0)
    assert apu.truth()["solar_w"] == pytest.approx(60.0)


def test_solar_mppt_with_insolation() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_solar_insolation_w(50.0, panel_temp_c=25.0)
    apu.step(1.0)
    assert apu.truth()["solar_w"] == pytest.approx(50.0 * 0.9, rel=1e-3)


def test_solar_panel_temp_derate() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_solar_insolation_w(50.0, panel_temp_c=45.0)
    apu.step(1.0)
    expected = 50.0 * 0.9 * (1.0 - 0.01 * 20.0)
    assert apu.truth()["solar_w"] == pytest.approx(expected, rel=1e-3)


def test_fuelcell_load_pct_drives_output() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_fuelcell_load_pct(0.8)
    apu.step(1.0)
    assert apu.truth()["fuelcell_w"] == pytest.approx(20.0)


def test_fuelcell_override_capped_at_continuous_w() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_fuelcell_w(100.0)
    apu.step(1.0)
    assert apu.truth()["fuelcell_w"] == pytest.approx(25.0)


def test_fuelcell_depletes_fuel() -> None:
    apu = ApuSubsystem(_profile(fuel_cell={
        "continuous_w": 25.0,
        "fuel_capacity_g": 100.0,
        "efficiency": 0.45,
        "wh_per_g_fuel": 2.5,
    }))
    apu.set_fuelcell_w(25.0)
    apu.step(3600.0)
    truth = apu.truth()
    assert truth["fuel_g"] == pytest.approx(100.0 - (25.0 / 2.5), rel=1e-3)
    assert truth["fuel_pct"] < 100.0


def test_fuelcell_stops_when_tank_empty() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_fuelcell_w(25.0)
    apu.step(3600.0 * 20.0)
    truth = apu.truth()
    assert truth["fuel_g"] == pytest.approx(0.0, abs=1e-3)
    apu.step(1.0)
    assert apu.truth()["fuelcell_w"] == 0.0


def test_fuelcell_refuel() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_fuelcell_w(25.0)
    apu.step(3600.0 * 20.0)
    apu.refuel(50.0)
    assert apu.truth()["fuel_g"] == pytest.approx(50.0)


def test_vehicle_disconnected_yields_zero() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_vehicle(connected=False, offered_w=100.0)
    apu.step(1.0)
    assert apu.truth()["vehicle_w"] == 0.0


def test_vehicle_offered_capped_by_current_limit() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_vehicle(connected=True, offered_w=500.0)
    apu.step(1.0)
    assert apu.truth()["vehicle_w"] == pytest.approx(28.0 * 5.0)


def test_vehicle_under_limit_returns_offered() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_vehicle(connected=True, offered_w=30.0)
    apu.step(1.0)
    assert apu.truth()["vehicle_w"] == pytest.approx(30.0)


def test_usbc_disconnected_yields_zero() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_usb_c_pd(connected=False, profile_w=60.0)
    apu.step(1.0)
    assert apu.truth()["usbc_w"] == 0.0


def test_usbc_picks_largest_profile_at_or_below_request() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_usb_c_pd(connected=True, profile_w=50.0)
    apu.step(1.0)
    assert apu.truth()["usbc_w"] == pytest.approx(45.0)


def test_usbc_falls_back_to_smallest_profile_when_request_too_low() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_usb_c_pd(connected=True, profile_w=5.0)
    apu.step(1.0)
    assert apu.truth()["usbc_w"] == pytest.approx(15.0)


def test_total_is_sum_of_sources() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_solar_w(10.0)
    apu.set_fuelcell_w(20.0)
    apu.set_vehicle(connected=True, offered_w=15.0)
    apu.set_usb_c_pd(connected=True, profile_w=27.0)
    apu.step(1.0)
    total = apu.total_w
    assert total == pytest.approx(10.0 + 20.0 + 15.0 + 27.0)


def test_usbc_default_profile_negotiated_at_construction() -> None:
    apu = ApuSubsystem(
        {
            "apu": {
                "usb_c_pd": {
                    "profiles_w": [15.0, 27.0, 45.0],
                    "default_profile_w": 50.0,
                },
            }
        }
    )
    apu.set_usb_c_pd(connected=True)
    apu.step(1.0)
    assert apu.truth()["usbc_w"] == pytest.approx(45.0)


def test_fuelcell_wh_per_g_derived_from_efficiency_when_unset() -> None:
    apu = ApuSubsystem(
        {
            "apu": {
                "fuel_cell": {
                    "continuous_w": 25.0,
                    "fuel_capacity_g": 100.0,
                    "efficiency": 0.40,
                },
            }
        }
    )
    apu.set_fuelcell_w(25.0)
    apu.step(3600.0)
    truth = apu.truth()
    expected_wh_per_g = 0.40 * 5.53
    expected_burn = 25.0 / expected_wh_per_g
    assert truth["fuel_g"] == pytest.approx(100.0 - expected_burn, rel=1e-3)


def test_legacy_flat_profile_fields_still_parsed() -> None:
    apu = ApuSubsystem(
        {
            "apu": {
                "solar_w_peak": 80.0,
                "fuelcell_w_continuous": 12.0,
                "fuelcell_fuel_capacity_g": 50.0,
            }
        }
    )
    apu.set_solar_w(50.0)
    apu.set_fuelcell_w(12.0)
    apu.step(1.0)
    assert apu.truth()["solar_w"] == pytest.approx(50.0)
    assert apu.truth()["fuelcell_w"] == pytest.approx(12.0)


def test_sensor_obs_includes_all_sources() -> None:
    apu = ApuSubsystem(_profile())
    apu.set_solar_w(10.0)
    apu.set_fuelcell_w(5.0)
    apu.step(1.0)
    obs = apu.sensor_obs()
    assert obs.source == "apu"
    for key in ("solar_w", "fuelcell_w", "vehicle_w", "usbc_w", "total_w"):
        assert key in obs.payload
        assert f"{key}_sigma" in obs.noise
