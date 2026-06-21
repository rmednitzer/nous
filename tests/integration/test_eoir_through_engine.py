"""Engine integration: the EO/IR payload reads ambient and feeds its estimator.

The EO/IR subsystem reads the environmental pack's ambient temperature and
humidity each tick (the seam the engine wires) and recomputes its per-band
detection-range envelope, which the paired Kalman filter then tracks. A scenario
that warms the environment toward the target temperature, or rolls a smoke
screen over the platform, watches the perception envelope close through the same
tick loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    return eng


def test_obscurant_closes_both_bands_through_tick(engine: Engine) -> None:
    engine.tick()
    eo_clear = engine.eoir.eo_range_m
    ir_clear = engine.eoir.ir_range_m
    engine.eoir.set_obscurant(1.0)  # heavy fog / dust / smoke
    for _ in range(10):
        engine.tick()
    assert engine.eoir.eo_range_m < eo_clear
    assert engine.eoir.ir_range_m < ir_clear


def test_warming_ambient_to_target_collapses_ir_contrast(engine: Engine) -> None:
    # The IR band loses contrast as the background warms toward the target: a
    # cross-subsystem effect routed through the environmental sensor pack.
    engine.sensors.set_temp_c(0.0)
    for _ in range(5):
        engine.tick()
    cold_ir = engine.eoir.ir_range_m
    engine.sensors.set_temp_c(32.0)  # thermal crossover with the default target
    for _ in range(5):
        engine.tick()
    assert engine.eoir.ir_range_m < cold_ir
    assert engine.eoir.ir_range_m == pytest.approx(0.0, abs=1.0)


def test_eoir_estimator_tracks_truth(engine: Engine) -> None:
    engine.eoir.set_obscurant(0.5)
    for _ in range(60):
        engine.tick()
    estimate = engine.eoir_est.state()
    assert estimate.point["eo_range_m"] == pytest.approx(
        engine.eoir.eo_range_m, abs=300.0
    )
    assert estimate.point["ir_range_m"] == pytest.approx(
        engine.eoir.ir_range_m, abs=300.0
    )


def test_snapshot_includes_eoir_block(engine: Engine) -> None:
    engine.tick()
    snap = engine.snapshot()
    assert "eoir" in snap
    assert "eo_range_m" in snap["eoir"]
    assert "ir_range_m" in snap["eoir"]
    assert "cal_factor" in snap["eoir"]


def test_eoir_seeds_reference_range_from_profile(tmp_nous_home: Path) -> None:
    profile = {
        "eoir": {"eo_r0_m": 5000.0},
        "power": {"capacity_wh": 100.0, "voltage_nominal_v": 14.4},
    }
    eng = Engine(profile=profile)
    # Clear air at the nominal ambient: the EO band sits at its reference range.
    assert eng.eoir.eo_range_m == pytest.approx(5000.0, rel=0.01)


def test_eoir_target_los_wired_through_engine(tmp_nous_home: Path) -> None:
    # With a world enabled, the engine wires terrain + position into the EO/IR
    # payload, so a configured target produces a real line-of-sight verdict.
    profile = {
        "world": {
            "enabled": True,
            "base_elevation_m": 0.0,
            "relief_m": 600.0,
            "feature_m": 3000.0,
            "seed": 3,
        },
        "power": {"capacity_wh": 100.0, "voltage_nominal_v": 14.4},
    }
    eng = Engine(profile=profile)
    eng.start()
    assert eng.terrain is not None
    eng.eoir.set_target(bearing_deg=90.0, range_m=4000.0, height_m=2.0)
    eng.tick()
    t = eng.eoir.truth()
    assert t["target_set"] is True
    assert isinstance(t["target_visible"], bool)  # terrain + position flowed through
    assert t["target_slant_m"] is not None
    assert t["target_slant_m"] == pytest.approx(4000.0, rel=0.05)
