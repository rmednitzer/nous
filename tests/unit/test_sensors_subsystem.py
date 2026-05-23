"""Environmental sensors subsystem: ground truth + profile-driven noise."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.sensors import SensorsSubsystem


def _profile(
    *,
    environmental: Mapping[str, Any] | None = None,
    thermal: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    out: dict[str, Any] = {}
    if environmental is not None:
        out["sensors"] = {"environmental": dict(environmental)}
    if thermal is not None:
        out["thermal"] = dict(thermal)
    return out


def test_defaults_when_environmental_section_missing() -> None:
    s = SensorsSubsystem({})
    assert s.temp_c == pytest.approx(22.0)
    assert s.humidity_pct == pytest.approx(50.0)
    assert s.baro_kpa == pytest.approx(101.3)


def test_seeded_from_environmental_defaults() -> None:
    s = SensorsSubsystem(
        _profile(
            environmental={
                "temp_c_default": -10.0,
                "humidity_pct_default": 80.0,
                "baro_kpa_default": 88.0,
            }
        )
    )
    assert s.temp_c == pytest.approx(-10.0)
    assert s.humidity_pct == pytest.approx(80.0)
    assert s.baro_kpa == pytest.approx(88.0)


def test_falls_back_to_thermal_ambient_when_no_env_default() -> None:
    s = SensorsSubsystem(_profile(thermal={"ambient_c_default": 35.0}))
    assert s.temp_c == pytest.approx(35.0)


def test_environmental_default_wins_over_thermal_default() -> None:
    s = SensorsSubsystem(
        _profile(
            environmental={"temp_c_default": -5.0},
            thermal={"ambient_c_default": 40.0},
        )
    )
    assert s.temp_c == pytest.approx(-5.0)


def test_set_temp_c_accepts_any_finite_value() -> None:
    s = SensorsSubsystem({})
    s.set_temp_c(-40.0)
    assert s.temp_c == pytest.approx(-40.0)
    s.set_temp_c(85.0)
    assert s.temp_c == pytest.approx(85.0)


def test_humidity_clamps_to_zero_one_hundred() -> None:
    s = SensorsSubsystem({})
    s.set_humidity_pct(-10.0)
    assert s.humidity_pct == pytest.approx(0.0)
    s.set_humidity_pct(125.0)
    assert s.humidity_pct == pytest.approx(100.0)


def test_baro_clamps_to_plausible_range() -> None:
    s = SensorsSubsystem({})
    s.set_baro_kpa(5.0)
    assert s.baro_kpa == pytest.approx(10.0)
    s.set_baro_kpa(500.0)
    assert s.baro_kpa == pytest.approx(200.0)


def test_observation_carries_profile_sigmas() -> None:
    s = SensorsSubsystem(
        _profile(
            environmental={
                "temp_c_sigma": 0.5,
                "humidity_pct_sigma": 2.0,
                "baro_kpa_sigma": 0.25,
            }
        )
    )
    obs = s.sensor_obs()
    assert obs.noise["temp_c_sigma"] == pytest.approx(0.5)
    assert obs.noise["humidity_pct_sigma"] == pytest.approx(2.0)
    assert obs.noise["baro_kpa_sigma"] == pytest.approx(0.25)


def test_observation_payload_matches_ground_truth() -> None:
    s = SensorsSubsystem({})
    s.set_temp_c(15.5)
    s.set_humidity_pct(42.0)
    s.set_baro_kpa(99.5)
    obs = s.sensor_obs()
    assert obs.payload["temp_c"] == pytest.approx(15.5)
    assert obs.payload["humidity_pct"] == pytest.approx(42.0)
    assert obs.payload["baro_kpa"] == pytest.approx(99.5)


def test_truth_includes_all_channels() -> None:
    s = SensorsSubsystem({})
    truth = s.truth()
    assert {"temp_c", "humidity_pct", "baro_kpa", "t"} <= set(truth)


def test_step_advances_subsystem_clock() -> None:
    s = SensorsSubsystem({})
    s.step(3.5)
    assert s.truth()["t"] == pytest.approx(3.5)
    s.step(-1.0)
    assert s.truth()["t"] == pytest.approx(3.5)
