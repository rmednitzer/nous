"""Engine integration: local inference reports cost and steers compute load.

These tests exercise the inference subsystem (BL-013, local path) end to
end through the real engine: a request returns a profile-derived
latency and joule figure, totals accumulate, and a sustained inference
rate set through the subsystem propagates into compute load (and from
there into both battery draw and thermal load via the existing
BL-007 wiring).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.power.set_soc_pct(60.0)
    eng.start()
    return eng


def test_local_request_returns_profile_latency_and_energy(engine: Engine) -> None:
    result = engine.inference.request_local("scan that radio for me", max_tokens=100)
    assert result.latency_s > 0.0
    assert result.energy_j > 0.0
    assert result.rate_tok_per_s == pytest.approx(
        engine.compute.tok_per_s_capacity
    )


def test_local_requests_accumulate_into_totals(engine: Engine) -> None:
    engine.inference.request_local("a", max_tokens=10)
    engine.inference.request_local("b", max_tokens=20)
    truth = engine.inference.truth()
    assert truth["local_calls"] == 2
    assert truth["total_tokens"] == 30


def test_continuous_rate_increases_compute_load(engine: Engine) -> None:
    capacity = engine.compute.tok_per_s_capacity
    engine.inference.set_continuous_rate(capacity * 0.75)
    engine.tick()
    assert engine.compute.load_pct == pytest.approx(75.0)
    assert engine.compute.draw_w > engine.compute.draw_w_idle


def test_continuous_inference_drains_battery_faster_than_idle(engine: Engine) -> None:
    engine.compute.set_load_pct(0.0)
    idle_start = engine.power.soc_pct
    for _ in range(120):
        engine.tick()
    idle_drop = idle_start - engine.power.soc_pct

    engine.power.set_soc_pct(60.0)
    engine.inference.set_continuous_rate(engine.compute.tok_per_s_capacity)
    busy_start = engine.power.soc_pct
    for _ in range(120):
        engine.tick()
    busy_drop = busy_start - engine.power.soc_pct

    assert busy_drop > idle_drop


def test_snapshot_includes_inference_summary(engine: Engine) -> None:
    engine.inference.request_local("hi", max_tokens=50)
    engine.tick()
    snap = engine.snapshot()
    assert "inference" in snap
    assert snap["inference"]["local_calls"] >= 1
    assert snap["inference"]["total_tokens"] >= 50
    assert snap["inference"]["total_energy_j"] > 0.0


def test_thermal_throttle_does_not_reduce_inference_metering(engine: Engine) -> None:
    """Throttle clips delivered load_pct, but a one-shot inference request
    still returns the profile's nominal latency / energy. The controller's
    job is to interpret total_energy_j against the actual draw_w
    history (which thermal throttling does shrink)."""
    engine.thermal.set_junction_c(engine.thermal.junction_temp_throttle + 1.0)
    engine.tick()
    result = engine.inference.request_local("hi", max_tokens=100)
    assert result.energy_j > 0.0
    assert result.rate_tok_per_s == pytest.approx(
        engine.compute.tok_per_s_capacity
    )


def test_engine_resets_clean(tmp_nous_home: Path) -> None:
    eng = Engine()
    eng.start()
    eng.inference.request_local("hi")
    fresh = Engine()
    assert fresh.inference.local_calls == 0
    assert fresh.inference.total_tokens == 0
