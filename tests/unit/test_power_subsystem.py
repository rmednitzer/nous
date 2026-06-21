"""Power subsystem: Li-ion physics under load, charge, and thermal derate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.power import PowerFlag, PowerSubsystem


def _profile(**overrides: Any) -> Mapping[str, Any]:
    base: dict[str, Any] = {
        "battery_wh": 100.0,
        "voltage_v_nominal": 12.0,
        "voltage_v_min": 10.0,
        "voltage_v_max": 14.0,
        "internal_resistance_ohm": 0.05,
        "rated_current_a": 5.0,
        "peukert_k": 1.10,
        "soc_pct_low_threshold": 20.0,
        "soc_pct_critical_threshold": 5.0,
        "thermal_derate_c": 45.0,
        "thermal_derate_slope_per_c": 0.05,
        "charge_limit_w": 50.0,
    }
    base.update(overrides)
    return {"power": base}


def test_starts_full() -> None:
    p = PowerSubsystem(_profile())
    assert p.soc_pct == pytest.approx(100.0)
    assert p.flag is PowerFlag.FULL
    assert p.remaining_wh == pytest.approx(100.0)


def test_load_discharges_soc() -> None:
    p = PowerSubsystem(_profile())
    p.set_load_w(60.0)
    for _ in range(60):
        p.step(1.0)
    truth = p.truth()
    assert truth["soc_pct"] < 100.0
    expected_wh = 60.0 * (60.0 / 3600.0)
    assert truth["remaining_wh"] == pytest.approx(100.0 - expected_wh, rel=0.05)


def test_charge_offsets_load_break_even() -> None:
    p = PowerSubsystem(_profile())
    p.set_load_w(30.0)
    p.set_charge_w(30.0)
    for _ in range(300):
        p.step(1.0)
    assert p.soc_pct == pytest.approx(100.0, abs=0.5)


def test_charge_recovers_soc() -> None:
    p = PowerSubsystem(_profile())
    p.set_soc_pct(50.0)
    p.set_load_w(10.0)
    p.set_charge_w(40.0)
    for _ in range(60):
        p.step(1.0)
    assert p.soc_pct > 50.0


def test_battery_records_the_regulated_charge_it_is_handed() -> None:
    # The bus-regulator clamp moved to the PMU (BL-005b / ADR 0075): the battery
    # records whatever charge it is delivered as both offered and accepted. The
    # charge_limit clamp is now exercised in tests/unit/test_pmu.py.
    p = PowerSubsystem(_profile())
    p.set_charge_w(35.0)
    truth = p.truth()
    assert truth["charge_offered_w"] == pytest.approx(35.0)
    assert truth["charge_accepted_w"] == pytest.approx(35.0)


def test_soc_clamps_at_zero() -> None:
    p = PowerSubsystem(_profile())
    p.set_soc_pct(1.0)
    p.set_load_w(80.0)
    for _ in range(120):
        p.step(1.0)
    assert p.soc_pct == pytest.approx(0.0)
    assert p.flag is PowerFlag.EMPTY


def test_low_flag_below_low_threshold() -> None:
    p = PowerSubsystem(_profile())
    p.set_soc_pct(15.0)
    assert p.flag is PowerFlag.LOW


def test_critical_flag_below_critical_threshold() -> None:
    p = PowerSubsystem(_profile())
    p.set_soc_pct(3.0)
    assert p.flag is PowerFlag.CRITICAL


def test_peukert_reduces_capacity_at_high_current() -> None:
    a = PowerSubsystem(_profile(peukert_k=1.0))
    b = PowerSubsystem(_profile(peukert_k=1.30))
    for sub in (a, b):
        sub.set_load_w(300.0)
        for _ in range(300):
            sub.step(1.0)
    assert b.soc_pct < a.soc_pct - 1.0


def test_peukert_not_applied_during_charging() -> None:
    a = PowerSubsystem(_profile(peukert_k=1.0))
    b = PowerSubsystem(_profile(peukert_k=1.30))
    for sub in (a, b):
        sub.set_soc_pct(50.0)
        sub.set_load_w(0.0)
        sub.set_charge_w(50.0)
        for _ in range(120):
            sub.step(1.0)
    assert b.soc_pct == pytest.approx(a.soc_pct, abs=0.1)


def test_thermal_derate_reduces_capacity() -> None:
    cold = PowerSubsystem(_profile())
    hot = PowerSubsystem(_profile())
    cold.set_load_w(40.0)
    hot.set_load_w(40.0)
    hot.set_cell_c(60.0)
    for _ in range(120):
        cold.step(1.0)
        hot.step(1.0)
    assert hot.soc_pct < cold.soc_pct


def test_endurance_min_positive_under_net_load() -> None:
    p = PowerSubsystem(_profile())
    p.set_soc_pct(80.0)
    p.set_load_w(40.0)
    endurance = p.endurance_min
    assert endurance is not None
    assert endurance == pytest.approx(120.0, rel=0.05)


def test_endurance_none_when_charging() -> None:
    p = PowerSubsystem(_profile())
    p.set_load_w(20.0)
    p.set_charge_w(20.0)
    assert p.endurance_min is None


def test_sensor_obs_carries_calibrated_noise() -> None:
    p = PowerSubsystem(_profile())
    obs = p.sensor_obs()
    assert obs.source == "power"
    assert "soc_pct" in obs.payload
    assert obs.noise["soc_pct_sigma"] > 0.0
    assert obs.noise["voltage_v_sigma"] > 0.0
