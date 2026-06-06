"""Tick-loop OpenTelemetry metrics (BL-037, ADR 0036).

The runtime instruments the tick loop with the OTel API only, so the
instruments are no-ops until a ``MeterProvider`` is configured. These tests
configure an SDK ``MeterProvider`` with an in-memory reader, drive the real
``tick_loop``, and assert the duration histogram and the overrun counter
record. No exporter and no network are involved; the instruments created at
import in ``nous.telemetry`` rebind to the provider set here.
"""

from __future__ import annotations

import time
from typing import Any

import anyio
import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from nous.engine import Engine
from nous.tick import tick_loop


@pytest.fixture(scope="module")
def reader() -> Any:
    """Install one SDK MeterProvider for this module and return its reader.

    ``set_meter_provider`` is process-global and honours only the first call,
    so this is the single place in the suite that sets a meter provider.
    """
    rdr = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[rdr]))
    return rdr


def _histogram_count(rdr: Any, name: str) -> int:
    total = 0
    data = rdr.get_metrics_data()
    if data is None:
        return 0
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    for point in metric.data.data_points:
                        total += int(getattr(point, "count", 0))
    return total


def _counter_value(rdr: Any, name: str) -> int:
    total = 0
    data = rdr.get_metrics_data()
    if data is None:
        return 0
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    for point in metric.data.data_points:
                        total += int(getattr(point, "value", 0))
    return total


async def test_tick_loop_records_duration(engine: Engine, reader: Any) -> None:
    before = _histogram_count(reader, "nous.tick.duration")
    stop = anyio.Event()
    with anyio.move_on_after(2.0):
        async with anyio.create_task_group() as tg:
            tg.start_soon(tick_loop, engine, 200.0, stop)
            await anyio.sleep(0.05)
            stop.set()
    assert _histogram_count(reader, "nous.tick.duration") > before


async def test_tick_loop_counts_overruns(
    engine: Engine, reader: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_tick = engine.tick

    def slow_tick() -> object:
        time.sleep(0.005)  # exceed the 1 ms budget at hz=1000 -> overrun
        return real_tick()

    monkeypatch.setattr(engine, "tick", slow_tick)
    before = _counter_value(reader, "nous.tick.overruns")
    stop = anyio.Event()
    with anyio.move_on_after(2.0):
        async with anyio.create_task_group() as tg:
            tg.start_soon(tick_loop, engine, 1000.0, stop)
            await anyio.sleep(0.05)
            stop.set()
    assert _counter_value(reader, "nous.tick.overruns") > before
