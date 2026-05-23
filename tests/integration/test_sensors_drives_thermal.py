"""Engine integration: sensors subsystem is the ambient source for thermal.

The environmental sensor pack carries the ambient temperature ground
truth. The engine reads `sensors.temp_c` each tick and feeds it into
the thermal subsystem's `set_ambient_c`, so a scenario that calls
`engine.sensors.set_temp_c(...)` watches enclosure cooling, junction
heatup, and the battery cell temperature track the new environment.
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


def test_sensors_temp_drives_thermal_ambient(engine: Engine) -> None:
    engine.sensors.set_temp_c(-15.0)
    engine.tick()
    assert engine.thermal.ambient_c == pytest.approx(-15.0)


def test_warmer_ambient_drives_higher_enclosure_temp(engine: Engine) -> None:
    engine.compute.set_load_pct(50.0)
    engine.sensors.set_temp_c(5.0)
    for _ in range(120):
        engine.tick()
    cold_enclosure = engine.thermal.enclosure_c

    engine.sensors.set_temp_c(40.0)
    for _ in range(120):
        engine.tick()
    hot_enclosure = engine.thermal.enclosure_c

    assert hot_enclosure > cold_enclosure


def test_sensors_estimator_tracks_truth(engine: Engine) -> None:
    engine.sensors.set_temp_c(10.0)
    engine.sensors.set_humidity_pct(35.0)
    for _ in range(60):
        engine.tick()
    estimate = engine.sensors_est.state()
    truth = engine.sensors.truth()
    assert estimate.point["temp_c"] == pytest.approx(truth["temp_c"], abs=0.5)
    assert estimate.point["humidity_pct"] == pytest.approx(
        truth["humidity_pct"], abs=2.0
    )


def test_snapshot_includes_sensors_block(engine: Engine) -> None:
    engine.sensors.set_baro_kpa(85.0)
    engine.tick()
    snap = engine.snapshot()
    assert "sensors" in snap
    assert snap["sensors"]["baro_kpa"] == pytest.approx(85.0)
    assert "temp_c" in snap["sensors"]
    assert "humidity_pct" in snap["sensors"]


def test_default_ambient_seeds_from_profile_thermal(tmp_nous_home: Path) -> None:
    profile = {
        "thermal": {"ambient_c_default": 30.0},
        "power": {"capacity_wh": 100.0, "voltage_nominal_v": 14.4},
    }
    eng = Engine(profile=profile)
    assert eng.sensors.temp_c == pytest.approx(30.0)
    eng.tick()
    assert eng.thermal.ambient_c == pytest.approx(30.0)
