"""Engine + tool integration for the BL-005b PMU/PDU."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nous.config import Settings
from nous.engine import Engine
from nous.server import build_app
from nous.subsystems.pmu import Slot


def _payload(result: Any) -> dict[str, Any]:
    content, _ = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_pmu_status_tool(config: Settings) -> None:
    app = build_app(config)
    out = _payload(await app.mcp.call_tool("pmu_status", {}))
    assert "charge_limit_w" in out
    assert out["active_slot"] == "primary"
    assert out["charge_mode"] in {"cc", "cv", "idle"}
    assert out["primary_present"] is True


def test_secondary_slot_takes_over_when_primary_depletes(tmp_nous_home: Path) -> None:
    # A profile with a secondary slot: drain the primary, and the PMU hands the bus
    # to the charged secondary, so the device stays alive across the pack swap with
    # no bus collapse (BL-005b dual-slot hot-swap).
    profile = {
        "name": "dual-slot-test",
        "power": {"battery_wh": 50.0, "charge_limit_w": 100.0},
        "pmu": {"secondary": {"battery_wh": 50.0}},
    }
    eng = Engine(profile=profile, seed=0)
    eng.start()
    eng.power.set_soc_pct(0.5)  # primary nearly empty
    eng.compute.set_load_pct(100.0)
    for _ in range(200):
        eng.tick()
    assert eng.pmu.active_slot is Slot.SECONDARY
    assert eng.pmu.truth()["swaps"] >= 1
    assert eng.power.soc_pct > 0.0  # the device is still powered, off the second pack


def test_no_secondary_means_no_swap(tmp_nous_home: Path) -> None:
    profile = {
        "name": "single-slot-test",
        "power": {"battery_wh": 50.0, "charge_limit_w": 100.0},
    }
    eng = Engine(profile=profile, seed=0)
    eng.start()
    eng.power.set_soc_pct(0.5)
    eng.compute.set_load_pct(100.0)
    for _ in range(200):
        eng.tick()
    assert eng.pmu.active_slot is Slot.PRIMARY
    assert eng.pmu.truth()["swaps"] == 0
