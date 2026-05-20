"""Async tick loop driving the simulator engine."""

from __future__ import annotations

import anyio

from .engine import Engine

__all__ = ["tick_loop"]


async def tick_loop(engine: Engine, hz: float, stop: anyio.Event) -> None:
    """Wake at ``1/hz`` cadence and advance ``engine.tick()`` until ``stop`` fires.

    Backpressure: if a tick takes longer than its budget we skip the sleep
    and run the next tick immediately, logging the overrun count on the
    engine state.
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
    engine.state.last_capabilities["tick_overruns"] = float(overruns)
