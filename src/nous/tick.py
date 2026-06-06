"""Async tick loop driving the simulator engine."""

from __future__ import annotations

import anyio
import anyio.lowlevel

from .engine import Engine
from .telemetry import tick_duration, tick_overruns

__all__ = ["tick_loop"]


async def tick_loop(engine: Engine, hz: float, stop: anyio.Event) -> None:
    """Wake at ``1/hz`` cadence and advance ``engine.tick()`` until ``stop`` fires.

    Backpressure: if a tick takes longer than its budget we skip the sleep
    and run the next tick immediately, logging the overrun count on the
    engine state. The overrun branch still hits a checkpoint so the loop
    cannot starve the event loop or refuse cancellation; without it a
    sustained overrun would block MCP request handling and graceful
    shutdown of the server.

    The budget timer reads ``engine.clock.monotonic()`` per ADR 0019
    (the engine owns the time source). Under the default
    ``MonotonicClock`` this is value-identical to
    ``anyio.current_time()`` on the asyncio backend; under a
    ``VirtualClock`` driven from a test, the engine clock will not
    advance during ``engine.tick()``, so ``elapsed`` is zero, the
    budget is ``dt``, and ``anyio.move_on_after`` waits the full
    inter-tick interval in real time. That keeps cancellation
    semantics intact regardless of the injected clock.
    """
    if hz <= 0.0:
        raise ValueError("hz must be positive")
    dt = 1.0 / hz
    overruns = 0
    while not stop.is_set():
        t0 = engine.clock.monotonic()
        engine.tick()
        elapsed = engine.clock.monotonic() - t0
        # OTel metrics (BL-037, ADR 0036): no-op until a provider is configured.
        tick_duration.record(elapsed, {"nous.tick.mode": str(engine.state.mode.value)})
        budget = dt - elapsed
        if budget > 0:
            with anyio.move_on_after(budget):
                await stop.wait()
        else:
            overruns += 1
            tick_overruns.add(1)
            await anyio.lowlevel.checkpoint()
    engine.state.last_capabilities["tick_overruns"] = float(overruns)
