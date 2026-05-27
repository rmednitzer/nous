"""Engine integration: comms subsystem drives FSM CommsState each tick.

The CommsSubsystem is the live ground truth for link availability; the
engine consults it each tick and updates ``state.comms_state`` via the
:func:`derive` aggregator from ADR-0006. Cloud-bound flows (inference
fallback, comms_send) gate on the resulting label.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine
from nous.state.comms_state import CommsState


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    return eng


def test_engine_initial_state_is_connected_when_links_present(engine: Engine) -> None:
    assert engine.state.comms_state is CommsState.CONNECTED


def test_aging_out_all_links_transitions_to_denied(engine: Engine) -> None:
    max_age = max(link.max_age_s for link in engine.comms)
    ticks = int((max_age + 5.0) / engine.dt_s) + 2
    for _ in range(ticks):
        engine.tick()
    assert engine.state.comms_state is CommsState.DENIED


def test_tx_on_link_keeps_it_alive(engine: Engine) -> None:
    link_id = engine.comms.link_ids[0]
    link = engine.comms.link(link_id)
    assert link is not None
    max_age = link.max_age_s
    ticks = int((max_age - 1.0) / engine.dt_s)
    for _ in range(ticks):
        engine.comms.tx(link_id, 1024)
        engine.tick()
    link_after = engine.comms.link(link_id)
    assert link_after is not None
    assert link_after.is_live() is True


def test_scenario_forced_disconnect_propagates_to_engine_state(engine: Engine) -> None:
    for link_id in engine.comms.link_ids:
        engine.comms.set_link_state(link_id, connected=False)
    engine.tick()
    assert engine.state.comms_state is CommsState.DENIED


def test_partial_outage_degrades_to_limited(engine: Engine) -> None:
    link_ids = engine.comms.link_ids
    if len(link_ids) < 2:
        pytest.skip("need >=2 links to express partial outage")
    engine.comms.set_link_state(link_ids[0], loss_pct=80.0)
    engine.tick()
    assert engine.state.comms_state is CommsState.LIMITED


def test_comms_estimator_tracks_link_count(engine: Engine) -> None:
    engine.tick()
    estimate = engine.comms_est.state()
    assert estimate.point["total_links"] == pytest.approx(
        float(len(engine.comms.link_ids))
    )


def test_snapshot_includes_comms_summary(engine: Engine) -> None:
    engine.tick()
    snap = engine.snapshot()
    assert "comms" in snap
    assert snap["comms"]["state"] == engine.state.comms_state.value
    assert snap["comms"]["link_count"] == len(engine.comms.link_ids)


def test_engine_with_no_comms_section_starts_denied(tmp_nous_home: Path) -> None:
    eng = Engine(profile={"comms": None})
    assert eng.state.comms_state is CommsState.DENIED
