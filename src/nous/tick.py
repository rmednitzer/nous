"""Async tick loop driving the simulator engine."""

from __future__ import annotations

import anyio
import anyio.lowlevel

from .engine import Engine

__all__ = ["tick_loop"]


async def tick_loop(engine: Engine, hz: float, stop: anyio.Event) -> None:
    """Wake at ``1/hz`` cadence and advance ``engine.tick()`` until ``stop`` fires.

    Backpressure: if a tick takes longer than its budget we skip the sleep
    and run the next tick immediately, logging the overrun count on the
    engine state. The overrun branch still hits a checkpoint so the loop
    cannot starve the event loop or refuse cancellation; without it a
    sustained overrun would block MCP request handling and graceful
    shutdown of the server.
    """
    if hz <= 0.0:
        raise ValueError("hz must be positive")
    dt = 1.0 / hz
    overruns = 0
    while not stop.is_set():
        t0 = anyio.current_time()
        engine.tick()
        elapsed = anyio.current_time() - t0
        budget = dt - elapsed
        if budget > 0:
            with anyio.move_on_after(budget):
                await stop.wait()
        else:
            overruns += 1
            await anyio.lowlevel.checkpoint()
    engine.state.last_capabilities["tick_overruns"] = float(overruns)
