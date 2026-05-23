"""Biometrics subsystem: ground truth, clamps, profile-driven sigmas."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.biometrics import BiometricsSubsystem


def _profile(**overrides: Any) -> Mapping[str, Any]:
    base: dict[str, Any] = {
        "heart_rate_bpm_sigma": 2.0,
        "core_temp_c_sigma": 0.05,
        "hydration_pct_sigma": 1.0,
    }
    base.update(overrides)
    return {"sensors": {"biometrics": base}}


def test_defaults_when_biometrics_section_missing() -> None:
    b = BiometricsSubsystem({})
    assert b.heart_rate_bpm == pytest.approx(70.0)
    assert b.core_temp_c == pytest.approx(37.0)
    assert b.hydration_pct == pytest.approx(90.0)
    assert b.cognitive_load == pytest.approx(0.2)


def test_seeded_from_biometrics_defaults() -> None:
    b = BiometricsSubsystem(
        _profile(
            heart_rate_bpm_default=120.0,
            core_temp_c_default=38.5,
            hydration_pct_default=65.0,
            cognitive_load_default=0.7,
        )
    )
    assert b.heart_rate_bpm == pytest.approx(120.0)
    assert b.core_temp_c == pytest.approx(38.5)
    assert b.hydration_pct == pytest.approx(65.0)
    assert b.cognitive_load == pytest.approx(0.7)


def test_heart_rate_clamps_to_physiological_range() -> None:
    b = BiometricsSubsystem(_profile())
    b.set_heart_rate_bpm(5.0)
    assert b.heart_rate_bpm == pytest.approx(20.0)
    b.set_heart_rate_bpm(500.0)
    assert b.heart_rate_bpm == pytest.approx(240.0)


def test_core_temp_clamps_to_physiological_range() -> None:
    b = BiometricsSubsystem(_profile())
    b.set_core_temp_c(10.0)
    assert b.core_temp_c == pytest.approx(28.0)
    b.set_core_temp_c(60.0)
    assert b.core_temp_c == pytest.approx(44.0)


def test_hydration_clamps_to_zero_one_hundred() -> None:
    b = BiometricsSubsystem(_profile())
    b.set_hydration_pct(-10.0)
    assert b.hydration_pct == pytest.approx(0.0)
    b.set_hydration_pct(150.0)
    assert b.hydration_pct == pytest.approx(100.0)


def test_cognitive_load_clamps_to_unit_interval() -> None:
    b = BiometricsSubsystem(_profile())
    b.set_cognitive_load(-0.5)
    assert b.cognitive_load == pytest.approx(0.0)
    b.set_cognitive_load(2.0)
    assert b.cognitive_load == pytest.approx(1.0)


def test_observation_carries_profile_sigmas() -> None:
    b = BiometricsSubsystem(
        _profile(
            heart_rate_bpm_sigma=3.0,
            core_temp_c_sigma=0.10,
            hydration_pct_sigma=2.0,
            cognitive_load_sigma=0.08,
        )
    )
    obs = b.sensor_obs()
    assert obs.noise["heart_rate_bpm_sigma"] == pytest.approx(3.0)
    assert obs.noise["core_temp_c_sigma"] == pytest.approx(0.10)
    assert obs.noise["hydration_pct_sigma"] == pytest.approx(2.0)
    assert obs.noise["cognitive_load_sigma"] == pytest.approx(0.08)


def test_observation_payload_matches_ground_truth() -> None:
    b = BiometricsSubsystem(_profile())
    b.set_heart_rate_bpm(140.0)
    b.set_core_temp_c(39.0)
    obs = b.sensor_obs()
    assert obs.payload["heart_rate_bpm"] == pytest.approx(140.0)
    assert obs.payload["core_temp_c"] == pytest.approx(39.0)


def test_truth_includes_all_channels() -> None:
    b = BiometricsSubsystem(_profile())
    truth = b.truth()
    assert {
        "heart_rate_bpm",
        "core_temp_c",
        "hydration_pct",
        "cognitive_load",
        "t",
    } <= set(truth)


def test_step_advances_clock_only_for_positive_dt() -> None:
    b = BiometricsSubsystem(_profile())
    b.step(2.0)
    assert b.truth()["t"] == pytest.approx(2.0)
    b.step(-1.0)
    assert b.truth()["t"] == pytest.approx(2.0)


def test_init_seeded_value_clamped_to_envelope() -> None:
    b = BiometricsSubsystem(
        _profile(
            heart_rate_bpm_default=1000.0,
            core_temp_c_default=60.0,
            hydration_pct_default=200.0,
            cognitive_load_default=10.0,
        )
    )
    assert b.heart_rate_bpm == pytest.approx(240.0)
    assert b.core_temp_c == pytest.approx(44.0)
    assert b.hydration_pct == pytest.approx(100.0)
    assert b.cognitive_load == pytest.approx(1.0)
