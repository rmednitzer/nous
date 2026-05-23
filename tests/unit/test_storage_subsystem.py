"""Storage subsystem: write accounting, wear curve, capacity clamp."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.storage import StorageSubsystem


def _profile(**overrides: Any) -> Mapping[str, Any]:
    base: dict[str, Any] = {
        "capacity_gib": 1024.0,
        "wear_pct_initial": 0.0,
        "write_amplification": 1.2,
    }
    base.update(overrides)
    return {"storage": base}


def test_starts_empty_with_initial_wear() -> None:
    s = StorageSubsystem(_profile(wear_pct_initial=2.5))
    assert s.used_gib == pytest.approx(0.0)
    assert s.wear_pct == pytest.approx(2.5)
    assert s.free_gib == pytest.approx(1024.0)


def test_write_increases_used_and_wear() -> None:
    s = StorageSubsystem(_profile())
    before_wear = s.wear_pct
    s.write(100.0)
    assert s.used_gib == pytest.approx(100.0)
    assert s.wear_pct > before_wear


def test_write_amplification_inflates_lifetime_writes() -> None:
    s = StorageSubsystem(_profile(write_amplification=2.0))
    s.write(50.0)
    assert s.lifetime_physical_gib == pytest.approx(100.0)


def test_write_clamps_to_free_space() -> None:
    s = StorageSubsystem(_profile(capacity_gib=10.0))
    accepted = s.write(25.0)
    assert accepted == pytest.approx(10.0)
    assert s.used_gib == pytest.approx(10.0)
    assert s.at_capacity is True


def test_subsequent_write_when_full_accepts_nothing() -> None:
    s = StorageSubsystem(_profile(capacity_gib=10.0))
    s.write(10.0)
    accepted = s.write(5.0)
    assert accepted == pytest.approx(0.0)


def test_negative_write_ignored() -> None:
    s = StorageSubsystem(_profile())
    accepted = s.write(-50.0)
    assert accepted == pytest.approx(0.0)
    assert s.used_gib == pytest.approx(0.0)


def test_used_pct_reflects_capacity_ratio() -> None:
    s = StorageSubsystem(_profile(capacity_gib=200.0))
    s.write(50.0)
    assert s.used_pct == pytest.approx(25.0)


def test_used_pct_zero_when_capacity_zero() -> None:
    s = StorageSubsystem(_profile(capacity_gib=0.0))
    assert s.used_pct == pytest.approx(0.0)
    assert s.at_capacity is True


def test_sustained_write_rate_accumulates_over_steps() -> None:
    s = StorageSubsystem(_profile())
    s.set_write_rate(2.0)  # 2 GiB/s
    s.step(5.0)
    assert s.used_gib == pytest.approx(10.0, abs=0.001)


def test_write_rate_clamps_negative_to_zero() -> None:
    s = StorageSubsystem(_profile())
    s.set_write_rate(-3.0)
    assert s.write_rate_gib_per_s == pytest.approx(0.0)


def test_wear_caps_at_one_hundred() -> None:
    s = StorageSubsystem(_profile(capacity_gib=1.0, tbw_gib=1.0))
    # Need to use the drive past 100% of TBW. Fill it, drain it, fill it again,
    # but the subsystem doesn't allow deletion -- so use a tiny TBW relative
    # to capacity so even a single fill exceeds it.
    s.write(1.0)
    assert s.wear_pct == pytest.approx(100.0)


def test_seeded_used_clamped_to_capacity() -> None:
    s = StorageSubsystem(_profile(capacity_gib=100.0))
    s.set_used_gib(250.0)
    assert s.used_gib == pytest.approx(100.0)
    s.set_used_gib(-5.0)
    assert s.used_gib == pytest.approx(0.0)


def test_default_tbw_scales_with_capacity_when_unset() -> None:
    s = StorageSubsystem(_profile(capacity_gib=512.0))
    assert s.tbw_gib == pytest.approx(512.0 * 600.0)


def test_explicit_tbw_overrides_default() -> None:
    s = StorageSubsystem(_profile(tbw_gib=10000.0))
    assert s.tbw_gib == pytest.approx(10000.0)


def test_write_amplification_floor_of_one() -> None:
    s = StorageSubsystem(_profile(write_amplification=0.5))
    assert s.write_amplification == pytest.approx(1.0)


def test_truth_carries_capacity_and_flags() -> None:
    s = StorageSubsystem(_profile())
    truth = s.truth()
    assert truth["capacity_gib"] == pytest.approx(1024.0)
    assert "at_capacity" in truth
    assert "worn_out" in truth
    assert "lifetime_physical_gib" in truth


def test_sensor_obs_carries_calibrated_noise() -> None:
    s = StorageSubsystem(_profile())
    obs = s.sensor_obs()
    assert obs.source == "storage"
    assert obs.noise["used_gib_sigma"] > 0.0
    assert obs.noise["wear_pct_sigma"] > 0.0


def test_defaults_when_storage_section_missing() -> None:
    s = StorageSubsystem({})
    assert s.capacity_gib == pytest.approx(256.0)
    assert s.wear_pct == pytest.approx(0.0)
