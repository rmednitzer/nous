"""Engine integration: storage subsystem accumulates writes through the tick.

The storage subsystem participates in the engine tick loop alongside
the existing power / APU / thermal / compute / inference subsystems.
These tests verify that a sustained write rate accumulates used space
and wear over time, and that the storage estimator tracks the truth.
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


def test_sustained_write_rate_grows_used_space(engine: Engine) -> None:
    engine.storage.set_write_rate(1.0)  # 1 GiB/s
    start = engine.storage.used_gib
    ticks = 60
    for _ in range(ticks):
        engine.tick()
    expected = start + ticks * engine.dt_s
    assert engine.storage.used_gib == pytest.approx(expected, abs=0.1)


def test_sustained_write_rate_increases_wear(engine: Engine) -> None:
    start_wear = engine.storage.wear_pct
    engine.storage.set_write_rate(2.0)
    for _ in range(120):
        engine.tick()
    assert engine.storage.wear_pct > start_wear


def test_storage_estimator_tracks_used_space(engine: Engine) -> None:
    engine.storage.write(50.0)
    for _ in range(20):
        engine.tick()
    estimate = engine.storage_est.state()
    truth = engine.storage.truth()
    assert estimate.point["used_gib"] == pytest.approx(
        truth["used_gib"], abs=1.0
    )


def test_storage_estimator_tracks_wear(engine: Engine) -> None:
    engine.storage.set_write_rate(5.0)
    for _ in range(60):
        engine.tick()
    estimate = engine.storage_est.state()
    truth = engine.storage.truth()
    assert estimate.point["wear_pct"] == pytest.approx(
        truth["wear_pct"], abs=1.0
    )


def test_capacity_blocks_further_writes_in_loop(engine: Engine) -> None:
    capacity = engine.storage.capacity_gib
    engine.storage.set_used_gib(capacity - 5.0)
    engine.storage.set_write_rate(10.0)
    for _ in range(10):
        engine.tick()
    assert engine.storage.at_capacity is True
    assert engine.storage.used_gib == pytest.approx(capacity)


def test_snapshot_includes_storage_summary(engine: Engine) -> None:
    engine.storage.write(20.0)
    engine.tick()
    snap = engine.snapshot()
    assert "storage" in snap
    assert "used_gib" in snap["storage"]
    assert "wear_pct" in snap["storage"]
    assert "at_capacity" in snap["storage"]
    assert "worn_out" in snap["storage"]


def test_default_engine_storage_starts_empty(engine: Engine) -> None:
    assert engine.storage.used_gib == pytest.approx(0.0)
    assert engine.storage.wear_pct == pytest.approx(0.0)
