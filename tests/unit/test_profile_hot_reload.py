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
    assert summary["rebuilt_subsystems"] == 10


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
