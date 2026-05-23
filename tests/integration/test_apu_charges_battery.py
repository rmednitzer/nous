"""Engine integration: the APU charges the primary battery each tick.

These tests run the real :class:`Engine` (subsystem step + estimator
update + tick advance) and verify the auxiliary power loop closes
correctly. APU output flows into ``PowerSubsystem.set_charge_w`` and
restores SoC when load is light; the bus regulator clips an
over-generous source to ``charge_limit_w`` so the controller can
distinguish "offered" from "accepted" charge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.power.set_soc_pct(50.0)
    eng.start()
    return eng


def test_apu_recharges_when_load_is_zero(engine: Engine) -> None:
    engine.apu.set_solar_w(40.0)
    engine.compute.set_load_pct(0.0)
    for _ in range(120):
        engine.tick()
    assert engine.power.soc_pct > 50.0


def test_balanced_load_and_apu_holds_soc(engine: Engine) -> None:
    engine.compute.set_load_pct(25.0)
    engine.apu.set_solar_w(engine.compute.draw_w)
    start = engine.power.soc_pct
    for _ in range(120):
        engine.tick()
    assert engine.power.soc_pct == pytest.approx(start, abs=0.5)


def test_load_exceeding_apu_discharges_battery(engine: Engine) -> None:
    engine.apu.set_solar_w(5.0)
    engine.compute.set_load_pct(100.0)
    start = engine.power.soc_pct
    for _ in range(1200):
        engine.tick()
    assert engine.power.soc_pct < start - 1.0


def test_apu_total_clamped_by_charge_limit_in_truth(engine: Engine) -> None:
    engine.apu.set_solar_w(500.0)
    engine.tick()
    truth = engine.power.truth()
    assert truth["charge_offered_w"] >= truth["charge_accepted_w"]


def test_power_estimator_tracks_soc(engine: Engine) -> None:
    engine.compute.set_load_pct(15.0)
    for _ in range(60):
        engine.tick()
    estimate = engine.power_est.state()
    truth = engine.power.truth()
    assert estimate.point["soc_pct"] == pytest.approx(truth["soc_pct"], abs=1.0)


def test_apu_estimator_tracks_total(engine: Engine) -> None:
    engine.apu.set_solar_w(15.0)
    engine.apu.set_fuelcell_w(10.0)
    for _ in range(40):
        engine.tick()
    estimate = engine.apu_est.state()
    assert estimate.point["total_w"] == pytest.approx(25.0, abs=2.0)


def test_power_estimator_seeded_with_subsystem_voltage(tmp_nous_home: Path) -> None:
    eng = Engine()
    estimate = eng.power_est.state()
    truth = eng.power.truth()
    assert estimate.point["voltage_v"] == pytest.approx(truth["voltage_v"], abs=1e-6)
