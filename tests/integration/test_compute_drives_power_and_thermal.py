"""Engine integration: compute load propagates into power and thermal.

The compute subsystem (BL-007) is the authoritative load source. Each
tick the engine reads ``compute.draw_w`` and feeds it into both the
battery (electrical draw) and the thermal subsystem (heat dissipated
at the junction). When the thermal subsystem reports throttling, the
engine signals the compute subsystem to clip its delivered load, so a
hot device starts shedding work automatically.
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


def test_compute_draw_feeds_power_load(engine: Engine) -> None:
    engine.compute.set_load_pct(100.0)
    engine.tick()
    truth = engine.power.truth()
    assert truth["load_w"] == pytest.approx(engine.compute.draw_w, abs=1e-6)


def test_compute_draw_feeds_thermal_load(engine: Engine) -> None:
    engine.compute.set_load_pct(100.0)
    engine.tick()
    assert engine.thermal.load_w == pytest.approx(engine.compute.draw_w, abs=1e-6)


def test_increasing_load_increases_battery_discharge_rate(engine: Engine) -> None:
    engine.compute.set_load_pct(10.0)
    light_start = engine.power.soc_pct
    for _ in range(60):
        engine.tick()
    light_drop = light_start - engine.power.soc_pct

    engine.power.set_soc_pct(60.0)
    engine.compute.set_load_pct(100.0)
    heavy_start = engine.power.soc_pct
    for _ in range(60):
        engine.tick()
    heavy_drop = heavy_start - engine.power.soc_pct

    assert heavy_drop > light_drop


def test_thermal_throttle_clips_delivered_compute_load(engine: Engine) -> None:
    engine.compute.set_load_pct(100.0)
    engine.thermal.set_junction_c(engine.thermal.junction_temp_throttle + 1.0)
    engine.tick()
    assert engine.compute.throttled is True
    assert engine.compute.load_pct < engine.compute.requested_load_pct


def test_compute_estimator_tracks_truth(engine: Engine) -> None:
    engine.compute.set_load_pct(75.0)
    for _ in range(120):
        engine.tick()
    estimate = engine.compute_est.state()
    truth = engine.compute.truth()
    assert estimate.point["load_pct"] == pytest.approx(truth["load_pct"], abs=1.5)
    assert estimate.point["draw_w"] == pytest.approx(truth["draw_w"], abs=1.5)


def test_snapshot_includes_compute_summary(engine: Engine) -> None:
    engine.compute.set_load_pct(40.0)
    engine.tick()
    snap = engine.snapshot()
    assert "compute" in snap
    assert "load_pct" in snap["compute"]
    assert "draw_w" in snap["compute"]
    assert "throttled" in snap["compute"]


def test_default_load_pct_is_close_to_idle(engine: Engine) -> None:
    engine.tick()
    truth = engine.power.truth()
    assert truth["load_w"] == pytest.approx(
        engine.compute.draw_w, abs=1e-6
    )
    assert engine.compute.draw_w < engine.compute.draw_w_load
