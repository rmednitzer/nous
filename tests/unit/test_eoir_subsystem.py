"""Unit tests for the BL-055 EO/IR thermo-optical subsystem."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from nous.subsystems.eoir import EoirSubsystem


def _eoir(ambient: list[float] | None = None, **profile: Any) -> EoirSubsystem:
    cfg: dict[str, Any] = {"eoir": profile} if profile else {}
    if ambient is None:
        return EoirSubsystem(cfg)
    return EoirSubsystem(cfg, ambient_fn=lambda: (ambient[0], ambient[1]))


def test_reduces_to_clear_air_defaults() -> None:
    # No profile, no ambient seam: clear-air reference ranges, every factor unity.
    eoir = EoirSubsystem({})
    t = eoir.truth()
    assert t["eo_range_m"] == pytest.approx(12000.0)
    assert t["ir_range_m"] == pytest.approx(8000.0)
    assert t["atm_factor_eo"] == pytest.approx(1.0)
    assert t["atm_factor_ir"] == pytest.approx(1.0)
    assert t["ir_contrast_factor"] == pytest.approx(1.0)
    assert t["eo_illum_factor"] == pytest.approx(1.0)
    assert t["cal_factor"] == pytest.approx(1.0)


def test_humidity_shrinks_the_visible_band() -> None:
    ambient = [22.0, 50.0]
    eoir = _eoir(ambient)
    clear = eoir.eo_range_m
    ambient[1] = 95.0  # heavy haze
    eoir.step(0.5)
    assert eoir.eo_range_m < clear


def test_obscurant_shrinks_both_bands_and_ir_penetrates_better() -> None:
    eoir = _eoir([22.0, 50.0])
    eoir.set_obscurant(1.0)
    eoir.step(0.5)
    # Heavy fog collapses both, but LWIR penetrates obscurants better than EO.
    assert eoir.eo_range_m < 12000.0
    assert eoir.ir_range_m < 8000.0
    assert eoir.ir_range_m > eoir.eo_range_m


def test_thermal_crossover_zeroes_ir_contrast() -> None:
    ambient = [22.0, 50.0]
    eoir = _eoir(ambient, target_c=32.0, contrast_dt_ref_c=10.0)
    ambient[0] = 32.0  # background warms to the target: thermal crossover
    eoir.step(0.5)
    assert eoir.ir_range_m == pytest.approx(0.0, abs=1e-6)
    # EO is unaffected by thermal contrast.
    assert eoir.eo_range_m > 0.0


def test_night_collapses_eo_but_not_ir() -> None:
    eoir = _eoir([22.0, 50.0])
    ir_day = eoir.ir_range_m
    eoir.set_illumination(0.1)
    eoir.step(0.5)
    assert eoir.eo_range_m == pytest.approx(12000.0 * 0.1, rel=0.05)
    # IR works in the dark: unchanged by illumination.
    assert eoir.ir_range_m == pytest.approx(ir_day, rel=1e-6)


def test_calibration_drifts_down_then_recalibrate_restores_it() -> None:
    eoir = EoirSubsystem(
        {"eoir": {"cal_drift_per_s": 0.05}}, rng=np.random.default_rng(7)
    )
    for _ in range(50):
        eoir.step(0.5)
    assert eoir.cal_factor < 1.0
    assert eoir.cal_factor >= 0.3  # the floor default
    eoir.recalibrate()
    assert eoir.cal_factor == pytest.approx(1.0)


def test_no_drift_without_rng() -> None:
    eoir = EoirSubsystem({"eoir": {"cal_drift_per_s": 0.05}})  # no rng
    for _ in range(50):
        eoir.step(0.5)
    assert eoir.cal_factor == pytest.approx(1.0)


def test_drift_is_deterministic_under_seed() -> None:
    a = EoirSubsystem({"eoir": {"cal_drift_per_s": 0.05}}, rng=np.random.default_rng(3))
    b = EoirSubsystem({"eoir": {"cal_drift_per_s": 0.05}}, rng=np.random.default_rng(3))
    for _ in range(30):
        a.step(0.5)
        b.step(0.5)
    assert a.cal_factor == b.cal_factor


def test_johnson_dri_ranges_are_ordered() -> None:
    t = EoirSubsystem({}).truth()
    assert t["eo_range_m"] > t["eo_recognition_m"] > t["eo_identification_m"]
    assert t["ir_range_m"] > t["ir_recognition_m"] > t["ir_identification_m"]


def test_observation_payload_matches_truth() -> None:
    eoir = _eoir([24.0, 60.0])
    eoir.set_obscurant(0.3)
    eoir.step(0.5)
    truth = eoir.truth()
    obs = eoir.sensor_obs()
    assert obs.source == "eoir"
    assert obs.payload["eo_range_m"] == pytest.approx(truth["eo_range_m"])
    assert obs.payload["ir_range_m"] == pytest.approx(truth["ir_range_m"])


def test_degraded_calibration_widens_the_reported_sigma() -> None:
    eoir = EoirSubsystem(
        {"eoir": {"cal_drift_per_s": 0.05}}, rng=np.random.default_rng(5)
    )
    base = eoir.sensor_obs().noise["eo_range_m_sigma"]
    for _ in range(40):
        eoir.step(0.5)
    degraded = eoir.sensor_obs().noise["eo_range_m_sigma"]
    assert degraded > base


def test_set_seams_clamp_to_unit_interval() -> None:
    eoir = EoirSubsystem({})
    eoir.set_obscurant(5.0)
    assert eoir.obscurant == pytest.approx(1.0)
    eoir.set_obscurant(-2.0)
    assert eoir.obscurant == pytest.approx(0.0)
    eoir.set_illumination(9.0)
    assert eoir.illumination == pytest.approx(1.0)


def test_step_advances_clock_and_guards_nonpositive_dt() -> None:
    eoir = EoirSubsystem({})
    eoir.step(0.5)
    assert eoir.truth()["t"] == pytest.approx(0.5)
    eoir.step(0.0)
    eoir.step(-1.0)
    assert eoir.truth()["t"] == pytest.approx(0.5)
