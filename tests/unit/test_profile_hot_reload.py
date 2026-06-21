"""Tests for the BL-039 profile hot-reload path."""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    return eng


def test_reload_same_profile_returns_summary(engine: Engine) -> None:
    summary = engine.reload_profile()
    assert summary["profile"] == "jetson-agx-orin"
    assert summary["previous"] == "jetson-agx-orin"
    assert summary["rebuilt_subsystems"] == 11


def test_reload_preserves_fsm_mode(engine: Engine) -> None:
    starting_mode = engine.state.mode
    starting_tick = engine.state.tick
    engine.tick()
    engine.reload_profile()
    assert engine.state.mode is starting_mode
    assert engine.state.tick >= starting_tick


def test_reload_rebuilds_subsystem_objects(engine: Engine) -> None:
    old_power = engine.power
    engine.reload_profile()
    assert engine.power is not old_power
    assert engine.thermal is not None
    assert engine.compute is not None


def test_reload_missing_profile_raises(engine: Engine) -> None:
    with pytest.raises(FileNotFoundError):
        engine.reload_profile(name="not-a-profile-anywhere")


def test_engine_still_ticks_after_reload(engine: Engine) -> None:
    engine.reload_profile()
    starting_tick = engine.state.tick
    for _ in range(5):
        engine.tick()
    assert engine.state.tick == starting_tick + 5


def test_reload_resets_failsafe_streaks(engine: Engine) -> None:
    # AUDIT-2026-06-14 RLD-1: a debounce streak accrued under the old profile
    # must not survive a reload, which restarts the safety law against the new
    # physics.
    from nous.state.machine import REQ_OPERATOR

    engine._failsafe.observe({REQ_OPERATOR: True})
    engine._failsafe.observe({REQ_OPERATOR: True})
    assert engine._failsafe.streak(REQ_OPERATOR) > 0

    engine.reload_profile()
    assert engine._failsafe.streak(REQ_OPERATOR) == 0


def test_reload_refreshes_capability_cache(engine: Engine) -> None:
    # AUDIT-2026-06-14 RLD-1: a capability claim cached from the old profile
    # must not survive into a read taken before the next tick.
    engine.tick()
    engine.state.last_capabilities = {"stale_marker": 999.0}
    engine.reload_profile()
    assert "stale_marker" not in engine.state.last_capabilities
    assert engine.state.last_capabilities  # recomputed from the rebuilt estimators


def test_reload_fails_closed_on_a_malformed_section(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A section that passes top-level validation but crashes a subsystem
    # constructor must leave the previous profile and subsystems intact: the
    # rebuild is atomic (BL-103 / ADR 0069).
    old_profile = engine.profile
    old_comms = engine.comms
    old_power = engine.power
    bad = dict(engine.profile)
    bad["comms"] = "not-a-mapping"
    monkeypatch.setattr("nous.engine._load_profile", lambda _name: bad)
    with pytest.raises(AttributeError):
        engine.reload_profile(name="malformed")
    assert engine.profile is old_profile
    assert engine.comms is old_comms
    assert engine.power is old_power  # a subsystem built before the failure did not commit
