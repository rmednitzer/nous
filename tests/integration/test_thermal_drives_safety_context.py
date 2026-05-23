"""Engine integration: the thermal subsystem feeds the FSM safety context.

The two-state thermal model (BL-005) drives two downstream consumers:

* :meth:`Engine._safety_context` reads :attr:`thermal.headroom_c` so SC-2
  refuses a ``MISSION`` transition once the junction is hot.
* :meth:`PowerSubsystem.set_cell_c` is fed the enclosure temperature so
  the battery's Peukert + thermal derate respond to real heat soak
  rather than a static ambient constant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine
from nous.state.machine import Mode


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    return eng


def test_compute_load_heats_junction_above_ambient(engine: Engine) -> None:
    engine.compute.set_load_pct(100.0)
    for _ in range(120):
        engine.tick()
    assert engine.thermal.junction_c > engine.thermal.ambient_c + 5.0


def test_enclosure_drives_battery_cell_temperature(engine: Engine) -> None:
    engine.compute.set_load_pct(100.0)
    engine.thermal.set_enclosure_c(70.0)
    engine.tick()
    truth = engine.power.truth()
    assert truth["cell_c"] == pytest.approx(engine.thermal.enclosure_c, abs=0.1)


def test_hot_junction_refuses_mission_via_safety_context(engine: Engine) -> None:
    engine.thermal.set_junction_c(84.0)  # 1C headroom, threshold defaults to 5C
    engine.fsm.reset(Mode.IDLE)
    engine.state.mode = Mode.IDLE
    ok, mode, reason = engine.request_transition("mission")
    assert not ok
    assert mode is Mode.IDLE
    assert "below threshold" in reason


def test_cool_junction_admits_mission_via_safety_context(engine: Engine) -> None:
    engine.thermal.set_junction_c(30.0)
    engine.fsm.reset(Mode.IDLE)
    engine.state.mode = Mode.IDLE
    ok, mode, _reason = engine.request_transition("mission")
    assert ok
    assert mode is Mode.MISSION


def test_thermal_estimator_tracks_junction(engine: Engine) -> None:
    engine.compute.set_load_pct(25.0)
    for _ in range(120):
        engine.tick()
    estimate = engine.thermal_est.state()
    truth = engine.thermal.truth()
    assert estimate.point["junction_c"] == pytest.approx(
        truth["junction_c"], abs=1.5
    )
    assert estimate.point["enclosure_c"] == pytest.approx(
        truth["enclosure_c"], abs=1.0
    )


def test_snapshot_includes_thermal_summary(engine: Engine) -> None:
    engine.tick()
    snap = engine.snapshot()
    assert "thermal" in snap
    assert "junction_c" in snap["thermal"]
    assert "enclosure_c" in snap["thermal"]
    assert "headroom_c" in snap["thermal"]
    assert "throttling" in snap["thermal"]
