"""Engine-level test of the BL-048 propagation model via the demo profile (ADR 0053).

Drives the shipped ``profiles/propagation-demo.yaml`` through the engine: the
relay link's quality is solved from the geometry each tick, so moving the device
away from the relay degrades the link and the comms state, and moving it back
recovers both. Exercises the whole pipeline (link budget to observation to
particle filter to ``derive`` to FSM) end to end on the real artifact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine, _load_profile
from nous.state.comms_state import CommsState


@pytest.fixture
def demo_engine(tmp_nous_home: Path) -> Engine:
    eng = Engine(profile=_load_profile("propagation-demo"), seed=7)
    eng.start()
    for _ in range(3):
        eng.tick()
    return eng


def test_demo_profile_starts_connected_with_solved_geometry(demo_engine: Engine) -> None:
    link = demo_engine.comms.link("relay")
    assert link is not None
    assert link.propagation is not None
    # The first ticks solved the budget, so the diagnostics are populated.
    assert link.range_m is not None and link.range_m > 0.0
    assert link.path_loss_db is not None and link.path_loss_db > 0.0
    assert link.snr_db is not None
    # ~1.5 km west of the start, the link is healthy.
    assert link.loss_pct < 5.0
    assert link.capacity_bps > 0.25 * link.bandwidth_bps
    state, _ = demo_engine.comms.derive_state()
    assert state is CommsState.CONNECTED


def test_demo_link_degrades_as_device_drives_away(demo_engine: Engine) -> None:
    near = demo_engine.comms.link("relay")
    assert near is not None
    # Capture scalars: comms.link() returns the same object, mutated by tick.
    near_rssi, near_cap, near_loss = near.rssi_dbm, near.capacity_bps, near.loss_pct
    near_range = near.range_m
    assert near_range is not None

    demo_engine.position.set_position(47.0, 13.30, alt_m=500.0)
    for _ in range(6):
        demo_engine.tick()

    far = demo_engine.comms.link("relay")
    assert far is not None
    assert far.range_m is not None and far.range_m > near_range
    assert far.rssi_dbm < near_rssi
    assert far.capacity_bps < near_cap
    assert far.loss_pct > near_loss
    # Capacity has collapsed below the per-link health floor.
    assert far.capacity_bps <= 0.25 * far.bandwidth_bps
    state, _ = demo_engine.comms.derive_state()
    assert state in {CommsState.DEGRADED, CommsState.DENIED}


def test_demo_link_recovers_when_device_returns(demo_engine: Engine) -> None:
    demo_engine.position.set_position(47.0, 13.30, alt_m=500.0)
    for _ in range(6):
        demo_engine.tick()
    degraded, _ = demo_engine.comms.derive_state()
    assert degraded in {CommsState.DEGRADED, CommsState.DENIED}

    demo_engine.position.set_position(47.0, 13.0, alt_m=500.0)
    for _ in range(6):
        demo_engine.tick()
    link = demo_engine.comms.link("relay")
    assert link is not None
    assert link.capacity_bps > 0.25 * link.bandwidth_bps
    state, _ = demo_engine.comms.derive_state()
    assert state is CommsState.CONNECTED


def test_demo_comms_status_surfaces_propagation_diagnostics(demo_engine: Engine) -> None:
    truth = demo_engine.comms.truth()
    links = {entry["link_id"]: entry for entry in truth["links"]}
    relay = links["relay"]
    assert relay["propagation"] is True
    assert relay["range_m"] is not None
    assert relay["path_loss_db"] is not None
    assert relay["snr_db"] is not None
    assert relay["capacity_bps"] > 0.0
