"""Compute subsystem: load-curve interpolation, throttle clipping, inference rate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.compute import ComputeSubsystem


def _profile(**overrides: Any) -> Mapping[str, Any]:
    base: dict[str, Any] = {
        "draw_w_idle": 8.0,
        "draw_w_load": 60.0,
        "load_curve": [
            {"load_pct": 0, "draw_w": 8},
            {"load_pct": 25, "draw_w": 18},
            {"load_pct": 50, "draw_w": 35},
            {"load_pct": 75, "draw_w": 50},
            {"load_pct": 100, "draw_w": 60},
        ],
        "inference_local": {
            "tok_per_s_p50": 200.0,
            "energy_j_per_tok": 0.12,
        },
    }
    base.update(overrides)
    return {"compute": base}


def test_starts_at_idle_draw() -> None:
    c = ComputeSubsystem(_profile())
    assert c.load_pct == pytest.approx(5.0)
    assert c.draw_w == pytest.approx(10.0, abs=0.1)


def test_load_curve_endpoints() -> None:
    c = ComputeSubsystem(_profile())
    c.set_load_pct(0.0)
    assert c.draw_w == pytest.approx(8.0)
    c.set_load_pct(100.0)
    assert c.draw_w == pytest.approx(60.0)


def test_load_curve_interpolates_between_points() -> None:
    c = ComputeSubsystem(_profile())
    c.set_load_pct(37.5)  # halfway between 25 (18W) and 50 (35W)
    assert c.draw_w == pytest.approx(26.5, abs=0.01)


def test_load_pct_clamps_to_zero_one_hundred() -> None:
    c = ComputeSubsystem(_profile())
    c.set_load_pct(-10.0)
    assert c.load_pct == pytest.approx(0.0)
    assert c.draw_w == pytest.approx(8.0)
    c.set_load_pct(250.0)
    assert c.load_pct == pytest.approx(100.0)
    assert c.draw_w == pytest.approx(60.0)


def test_thermal_throttle_caps_delivered_load() -> None:
    c = ComputeSubsystem(_profile())
    c.set_load_pct(90.0)
    pre = c.draw_w
    c.set_thermal_throttle(throttling=True)
    assert c.load_pct < c.requested_load_pct
    assert c.draw_w < pre
    assert c.throttled is True


def test_clear_thermal_throttle_restores_delivered_load() -> None:
    c = ComputeSubsystem(_profile())
    c.set_load_pct(90.0)
    pre = c.draw_w
    c.set_thermal_throttle(throttling=True)
    c.clear_thermal_throttle()
    assert c.draw_w == pytest.approx(pre)
    assert c.throttled is False


def test_mode_load_ceiling_caps_delivered_load_and_preserves_request() -> None:
    # ADR 0029 entry action: the FSM-posture ceiling caps delivered load while
    # the controller's request is preserved, so recovery can lift it.
    c = ComputeSubsystem(_profile())
    c.set_load_pct(100.0)
    pre = c.draw_w
    c.set_mode_load_ceiling(15.0)
    assert c.load_pct == pytest.approx(15.0)
    assert c.requested_load_pct == pytest.approx(100.0)
    assert c.draw_w < pre
    assert c.throttled is True
    assert c.truth()["mode_load_ceiling_pct"] == pytest.approx(15.0)


def test_mode_load_ceiling_clear_restores_request() -> None:
    c = ComputeSubsystem(_profile())
    c.set_load_pct(100.0)
    pre = c.draw_w
    c.set_mode_load_ceiling(15.0)
    c.set_mode_load_ceiling(None)
    assert c.load_pct == pytest.approx(100.0)
    assert c.draw_w == pytest.approx(pre)
    assert c.throttled is False
    assert c.truth()["mode_load_ceiling_pct"] is None


def test_mode_ceiling_and_thermal_throttle_take_the_minimum() -> None:
    # Both ceilings active: delivered load is the min of the request and every
    # active cap, and clearing one leaves the other in force.
    c = ComputeSubsystem(_profile())
    c.set_load_pct(100.0)
    c.set_mode_load_ceiling(15.0)
    c.set_thermal_throttle(throttling=True)  # 60 % thermal ceiling
    assert c.load_pct == pytest.approx(15.0)  # mode ceiling is tighter
    c.set_mode_load_ceiling(None)
    assert c.load_pct == pytest.approx(60.0)  # thermal ceiling still binds
    c.clear_thermal_throttle()
    assert c.load_pct == pytest.approx(100.0)


def test_inference_rate_within_capacity() -> None:
    c = ComputeSubsystem(_profile())
    c.set_inference_rate(100.0)  # 50% of 200 tok/s capacity
    assert c.load_pct == pytest.approx(50.0)
    assert c.saturated is False


def test_inference_rate_above_capacity_saturates() -> None:
    c = ComputeSubsystem(_profile())
    c.set_inference_rate(500.0)  # well over 200 tok/s
    assert c.load_pct == pytest.approx(100.0)
    assert c.saturated is True


def test_inference_rate_noop_when_capacity_unset() -> None:
    c = ComputeSubsystem(_profile(inference_local=None))
    c.set_load_pct(20.0)
    c.set_inference_rate(50.0)
    assert c.load_pct == pytest.approx(20.0)


def test_energy_for_tokens_uses_profile_constant() -> None:
    c = ComputeSubsystem(_profile())
    assert c.energy_for_tokens(100.0) == pytest.approx(12.0)
    assert c.energy_for_tokens(-5.0) == pytest.approx(0.0)


def test_sensor_obs_carries_calibrated_noise() -> None:
    c = ComputeSubsystem(_profile())
    c.set_load_pct(50.0)
    obs = c.sensor_obs()
    assert obs.source == "compute"
    assert obs.payload["load_pct"] == pytest.approx(50.0)
    assert obs.noise["load_pct_sigma"] > 0.0


def test_defaults_when_compute_section_missing() -> None:
    c = ComputeSubsystem({})
    assert c.draw_w_idle == pytest.approx(5.0)
    assert c.draw_w_load == pytest.approx(25.0)
    c.set_load_pct(50.0)
    assert c.draw_w == pytest.approx(15.0, abs=0.1)


def test_load_curve_unsorted_is_normalised() -> None:
    profile = {
        "compute": {
            "draw_w_idle": 5.0,
            "draw_w_load": 25.0,
            "load_curve": [
                {"load_pct": 100, "draw_w": 25},
                {"load_pct": 0, "draw_w": 5},
                {"load_pct": 50, "draw_w": 15},
            ],
        }
    }
    c = ComputeSubsystem(profile)
    c.set_load_pct(50.0)
    assert c.draw_w == pytest.approx(15.0)
