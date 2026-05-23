"""Thermal subsystem: two-state lumped model under load, idle, and cooldown."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.thermal import ThermalSubsystem


def _profile(**overrides: Any) -> Mapping[str, Any]:
    base: dict[str, Any] = {
        "ambient_c_default": 25.0,
        "junction_temp_max": 95.0,
        "junction_temp_throttle": 85.0,
        "thermal_resistance_c_per_w": 0.30,
        "enclosure_to_ambient_resistance_c_per_w": 0.5,
        "enclosure_mass_kg": 1.2,
        "enclosure_specific_heat_j_per_kg_k": 900.0,
        "junction_heat_capacity_j_per_k": 5.0,
        "headroom_threshold_c": 5.0,
    }
    base.update(overrides)
    return {"thermal": base}


def _settle(t: ThermalSubsystem, *, ticks: int, dt: float = 1.0) -> None:
    for _ in range(ticks):
        t.step(dt)


def test_starts_at_ambient() -> None:
    t = ThermalSubsystem(_profile())
    assert t.junction_c == pytest.approx(25.0)
    assert t.enclosure_c == pytest.approx(25.0)
    assert t.ambient_c == pytest.approx(25.0)
    assert t.headroom_c == pytest.approx(60.0)
    assert not t.throttling


def test_load_heats_junction_fast() -> None:
    t = ThermalSubsystem(_profile())
    t.set_load_w(30.0)
    _settle(t, ticks=30, dt=0.1)  # 3 seconds, several junction time constants
    assert t.junction_c > 30.0
    assert t.enclosure_c == pytest.approx(25.0, abs=0.5)


def test_steady_state_matches_resistor_ladder() -> None:
    t = ThermalSubsystem(_profile())
    t.set_load_w(30.0)
    _settle(t, ticks=20000, dt=0.5)
    expected_enclosure = 25.0 + 30.0 * 0.5
    expected_junction = expected_enclosure + 30.0 * 0.30
    assert t.enclosure_c == pytest.approx(expected_enclosure, abs=0.3)
    assert t.junction_c == pytest.approx(expected_junction, abs=0.3)


def test_cooldown_returns_to_ambient() -> None:
    t = ThermalSubsystem(_profile())
    t.set_junction_c(80.0)
    t.set_enclosure_c(55.0)
    t.set_load_w(0.0)
    _settle(t, ticks=20000, dt=0.5)
    assert t.junction_c == pytest.approx(25.0, abs=0.5)
    assert t.enclosure_c == pytest.approx(25.0, abs=0.5)


def test_ambient_shift_drives_steady_state() -> None:
    t = ThermalSubsystem(_profile())
    t.set_load_w(20.0)
    t.set_ambient_c(40.0)
    _settle(t, ticks=20000, dt=0.5)
    expected_enclosure = 40.0 + 20.0 * 0.5
    expected_junction = expected_enclosure + 20.0 * 0.30
    assert t.enclosure_c == pytest.approx(expected_enclosure, abs=0.3)
    assert t.junction_c == pytest.approx(expected_junction, abs=0.3)


def test_throttling_flag_crosses_threshold() -> None:
    t = ThermalSubsystem(_profile())
    t.set_junction_c(90.0)
    assert t.throttling is True
    assert t.headroom_c < 0.0


def test_headroom_threshold_from_profile() -> None:
    t = ThermalSubsystem(_profile(headroom_threshold_c=10.0))
    assert t.headroom_threshold_c == pytest.approx(10.0)


def test_step_ignores_non_positive_dt() -> None:
    t = ThermalSubsystem(_profile())
    t.set_load_w(60.0)
    t.step(0.0)
    t.step(-1.0)
    assert t.junction_c == pytest.approx(25.0)
    assert t.enclosure_c == pytest.approx(25.0)


def test_sensor_obs_carries_calibrated_noise() -> None:
    t = ThermalSubsystem(_profile())
    obs = t.sensor_obs()
    assert obs.source == "thermal"
    assert obs.payload["junction_c"] == pytest.approx(25.0)
    assert obs.payload["enclosure_c"] == pytest.approx(25.0)
    assert obs.noise["junction_c_sigma"] > 0.0
    assert obs.noise["enclosure_c_sigma"] > 0.0


def test_truth_exposes_throttle_metadata() -> None:
    t = ThermalSubsystem(_profile())
    truth = t.truth()
    assert truth["junction_temp_throttle"] == pytest.approx(85.0)
    assert truth["junction_temp_max"] == pytest.approx(95.0)
    assert truth["throttling"] is False


def test_defaults_when_thermal_section_missing() -> None:
    t = ThermalSubsystem({})
    assert t.junction_c == pytest.approx(25.0)
    t.set_load_w(20.0)
    _settle(t, ticks=20000, dt=0.5)
    assert t.junction_c > 25.0
