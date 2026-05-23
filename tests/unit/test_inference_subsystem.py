"""Inference subsystem: latency, energy, totals, continuous-rate coupling."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.subsystems.compute import ComputeSubsystem
from nous.subsystems.inference import InferenceSubsystem


def _profile(
    *,
    tok_per_s: float = 200.0,
    energy_j: float = 0.12,
) -> Mapping[str, Any]:
    return {
        "compute": {
            "draw_w_idle": 8.0,
            "draw_w_load": 60.0,
            "load_curve": [
                {"load_pct": 0, "draw_w": 8},
                {"load_pct": 100, "draw_w": 60},
            ],
            "inference_local": {
                "tok_per_s_p50": tok_per_s,
                "energy_j_per_tok": energy_j,
            },
        }
    }


def test_request_returns_profile_derived_latency_and_energy() -> None:
    inf = InferenceSubsystem(_profile())
    result = inf.request_local("hello world", max_tokens=100)
    assert result.n_tokens == 100
    assert result.latency_s == pytest.approx(0.5)  # 100 / 200
    assert result.energy_j == pytest.approx(12.0)  # 100 * 0.12
    assert result.rate_tok_per_s == pytest.approx(200.0)


def test_request_clamps_max_tokens_to_at_least_one() -> None:
    inf = InferenceSubsystem(_profile())
    result = inf.request_local("hi", max_tokens=0)
    assert result.n_tokens == 1


def test_request_zero_capacity_yields_zero_latency_no_crash() -> None:
    inf = InferenceSubsystem(_profile(tok_per_s=0.0))
    result = inf.request_local("hi", max_tokens=50)
    assert result.latency_s == pytest.approx(0.0)
    assert result.energy_j == pytest.approx(50 * 0.12)


def test_totals_accumulate_across_requests() -> None:
    inf = InferenceSubsystem(_profile())
    inf.request_local("a", max_tokens=10)
    inf.request_local("b", max_tokens=20)
    assert inf.local_calls == 2
    assert inf.total_tokens == 30
    assert inf.total_energy_j == pytest.approx(30 * 0.12)


def test_continuous_rate_drives_compute_load() -> None:
    profile = _profile()
    compute = ComputeSubsystem(profile)
    inf = InferenceSubsystem(profile, compute=compute)
    inf.set_continuous_rate(100.0)  # 50% of 200 tok/s capacity
    assert compute.load_pct == pytest.approx(50.0)
    assert inf.continuous_rate == pytest.approx(100.0)


def test_continuous_rate_above_capacity_saturates_compute() -> None:
    profile = _profile()
    compute = ComputeSubsystem(profile)
    inf = InferenceSubsystem(profile, compute=compute)
    inf.set_continuous_rate(500.0)
    assert compute.load_pct == pytest.approx(100.0)
    assert compute.saturated is True


def test_continuous_rate_noop_without_compute_reference() -> None:
    inf = InferenceSubsystem(_profile())
    inf.set_continuous_rate(50.0)
    assert inf.continuous_rate == pytest.approx(50.0)


def test_continuous_rate_clamps_negative_to_zero() -> None:
    profile = _profile()
    compute = ComputeSubsystem(profile)
    inf = InferenceSubsystem(profile, compute=compute)
    inf.set_continuous_rate(-10.0)
    assert inf.continuous_rate == pytest.approx(0.0)


def test_saturated_flag_reflects_compute_state() -> None:
    profile = _profile()
    compute = ComputeSubsystem(profile)
    inf = InferenceSubsystem(profile, compute=compute)
    inf.set_continuous_rate(1000.0)  # forces compute saturation
    result = inf.request_local("hi", max_tokens=10)
    assert result.saturated is True


def test_response_includes_token_count_and_prompt_excerpt() -> None:
    inf = InferenceSubsystem(_profile())
    result = inf.request_local("hello there friend", max_tokens=42)
    assert "tokens=42" in result.response
    assert "hello there friend" in result.response


def test_truth_exposes_profile_constants() -> None:
    inf = InferenceSubsystem(_profile())
    truth = inf.truth()
    assert truth["tok_per_s_capacity"] == pytest.approx(200.0)
    assert truth["energy_j_per_tok"] == pytest.approx(0.12)


def test_defaults_when_inference_local_section_missing() -> None:
    inf = InferenceSubsystem({"compute": {}})
    result = inf.request_local("hi", max_tokens=10)
    assert result.rate_tok_per_s == pytest.approx(0.0)
    assert result.energy_j == pytest.approx(0.0)
    assert result.latency_s == pytest.approx(0.0)
