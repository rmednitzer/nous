"""Unit tests for the BL-005b PMU/PDU subsystem."""

from __future__ import annotations

from typing import Any

import pytest

from nous.subsystems.pmu import PmuSubsystem, Slot
from nous.subsystems.power import PowerSubsystem


def _profile(**pmu: Any) -> dict[str, Any]:
    profile: dict[str, Any] = {"power": {"battery_wh": 100.0, "charge_limit_w": 50.0}}
    if pmu:
        profile["pmu"] = pmu
    return profile


def _pmu(**pmu: Any) -> PmuSubsystem:
    return PmuSubsystem.from_profile(_profile(**pmu))


def test_charge_clamped_to_limit() -> None:
    pmu = _pmu(charge_limit_w=20.0)
    pmu.active_battery.set_soc_pct(50.0)  # below the CV knee: constant current
    accepted = pmu.regulate_charge(500.0)
    assert accepted == pytest.approx(20.0)
    assert pmu.charge_offered_w == pytest.approx(500.0)


def test_cc_below_knee_cv_taper_above() -> None:
    pmu = _pmu(charge_limit_w=40.0, cv_soc_pct=80.0)
    pmu.active_battery.set_soc_pct(50.0)
    pmu.regulate_charge(1000.0)
    assert pmu.truth()["charge_mode"] == "cc"
    assert pmu.charge_accepted_w == pytest.approx(40.0)
    pmu.active_battery.set_soc_pct(95.0)
    pmu.regulate_charge(1000.0)
    assert pmu.truth()["charge_mode"] == "cv"
    assert pmu.charge_accepted_w < 40.0  # tapered near full


def test_idle_when_nothing_offered() -> None:
    pmu = _pmu()
    pmu.regulate_charge(0.0)
    assert pmu.truth()["charge_mode"] == "idle"
    assert pmu.charge_accepted_w == 0.0


def test_remove_inactive_slot_without_bus_collapse() -> None:
    pmu = _pmu(secondary={"battery_wh": 100.0})
    assert pmu.slot_present(Slot.SECONDARY)
    active_before = pmu.active_battery
    assert pmu.remove_slot(Slot.SECONDARY) is True
    assert pmu.slot_present(Slot.SECONDARY) is False
    # The active (primary) bus is untouched: no collapse.
    assert pmu.active_battery is active_before
    assert pmu.active_slot is Slot.PRIMARY


def test_remove_active_slot_refused() -> None:
    pmu = _pmu(secondary={"battery_wh": 100.0})
    assert pmu.remove_slot(Slot.PRIMARY) is False  # would collapse the bus
    assert pmu.slot_present(Slot.PRIMARY) is True


def test_arbitrate_switches_to_charged_standby_on_depletion() -> None:
    pmu = _pmu(secondary={"battery_wh": 100.0})
    assert pmu.active_slot.value == "primary"
    pmu.active_battery.set_soc_pct(0.0)
    assert pmu.arbitrate() is True
    assert pmu.active_slot is Slot.SECONDARY
    assert pmu.active_battery.soc_pct > 0.0  # the device stays alive
    assert pmu.truth()["swaps"] == 1


def test_arbitrate_no_switch_without_a_charged_standby() -> None:
    pmu = _pmu()  # no secondary
    pmu.active_battery.set_soc_pct(0.0)
    assert pmu.arbitrate() is False
    assert pmu.active_slot is Slot.PRIMARY


def test_insert_and_switch_slot() -> None:
    pmu = _pmu()
    assert pmu.slot_present(Slot.SECONDARY) is False
    fresh = PowerSubsystem({"power": {"battery_wh": 100.0}})
    assert pmu.insert_slot(Slot.SECONDARY, fresh) is True
    assert pmu.insert_slot(Slot.SECONDARY, fresh) is False  # already occupied
    assert pmu.switch_active(Slot.SECONDARY) is True
    assert pmu.active_slot is Slot.SECONDARY
    assert pmu.truth()["swaps"] == 1


def test_no_secondary_by_default() -> None:
    pmu = _pmu()
    assert pmu.slot_present(Slot.PRIMARY) is True
    assert pmu.slot_present(Slot.SECONDARY) is False
    assert pmu.truth()["secondary_soc_pct"] is None
