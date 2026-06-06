"""Smoke tests: package import, version, engine instantiation."""

from __future__ import annotations

import nous
from nous.engine import Engine
from nous.state.machine import Mode


def test_version_is_a_string() -> None:
    assert isinstance(nous.__version__, str)
    assert nous.__version__


def test_engine_starts_and_advances_clock(engine: Engine) -> None:
    assert engine.state.tick == 0
    engine.tick()
    engine.tick()
    assert engine.state.tick == 2
    assert engine.state.ts_s > 0.0


def test_engine_settles_in_idle_after_start(engine: Engine) -> None:
    # start() completes bring-up STOWED -> BOOT -> IDLE (ADR 0039).
    assert engine.state.mode is Mode.IDLE
