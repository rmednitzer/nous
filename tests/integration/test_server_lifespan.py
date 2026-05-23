"""FastMCP lifespan drives engine ticks (AUDIT-2026-05-23 C3)."""

from __future__ import annotations

import anyio
import pytest

from nous.engine import Engine
from nous.server import build_server, tick_lifespan
from nous.state.machine import Mode


@pytest.mark.asyncio
async def test_tick_lifespan_advances_engine(engine: Engine) -> None:
    """``tick_lifespan`` runs ``tick_loop`` while open; ticks accumulate."""
    initial_tick = engine.state.tick
    async with tick_lifespan(engine, tick_hz=100.0):
        await anyio.sleep(0.1)
    assert engine.state.tick - initial_tick >= 5, (
        f"expected >=5 ticks at 100Hz over 100ms, "
        f"got {engine.state.tick - initial_tick}"
    )


@pytest.mark.asyncio
async def test_tick_lifespan_stops_engine_on_exit(engine: Engine) -> None:
    """Exiting the lifespan calls ``engine.stop()``; FSM lands on SHUTDOWN."""
    async with tick_lifespan(engine, tick_hz=50.0):
        await anyio.sleep(0.05)
    assert engine.state.mode is Mode.SHUTDOWN, (
        f"expected SHUTDOWN after lifespan exit, got {engine.state.mode}"
    )


@pytest.mark.asyncio
async def test_tick_lifespan_idempotent_stop(engine: Engine) -> None:
    """A second lifespan run on the same engine restarts and stops cleanly."""
    async with tick_lifespan(engine, tick_hz=100.0):
        await anyio.sleep(0.05)
    # ``Engine.start`` is idempotent and ``stop`` was just called; a second
    # lifespan must restart the engine and tick it again.
    engine.start()
    tick_after_restart = engine.state.tick
    async with tick_lifespan(engine, tick_hz=100.0):
        await anyio.sleep(0.1)
    assert engine.state.tick - tick_after_restart >= 3
    assert engine.state.mode is Mode.SHUTDOWN


@pytest.mark.asyncio
async def test_build_server_registers_lifespan(tmp_nous_home: object) -> None:
    """The FastMCP server constructed by ``build_server`` carries a lifespan."""
    server = build_server()
    # The MCP SDK exposes the registered lifespan on the underlying server.
    assert getattr(server, "_mcp_server", None) is not None
    # The lifespan callable is stored on the MCP server; a lifespan was
    # registered (the engine is no longer untickable).
    lifespan_factory = getattr(server._mcp_server, "lifespan", None)
    assert lifespan_factory is not None, "lifespan must be registered on FastMCP"


@pytest.mark.asyncio
async def test_tick_loop_yields_on_sustained_overrun(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``tick_loop`` stays cancellable when every tick exceeds the budget.

    The overrun branch must hit a checkpoint; without it the loop never
    awaits, never yields, and never observes cancellation. PR #40 P1
    review finding.
    """
    import time

    from nous.tick import tick_loop

    real_tick = engine.tick
    call_count = 0

    def slow_tick() -> object:
        nonlocal call_count
        call_count += 1
        time.sleep(0.01)
        return real_tick()

    monkeypatch.setattr(engine, "tick", slow_tick)

    stop = anyio.Event()
    with anyio.move_on_after(1.0) as scope:
        async with anyio.create_task_group() as tg:
            tg.start_soon(tick_loop, engine, 1000.0, stop)
            await anyio.sleep(0.05)
            tg.cancel_scope.cancel()
    assert not scope.cancelled_caught, (
        "tick_loop did not respond to cancellation within 1s; "
        "the overrun branch is starving the event loop"
    )
    assert call_count > 0, "expected at least one slow tick to have run"


@pytest.mark.asyncio
async def test_tick_lifespan_stops_engine_when_tick_task_crashes(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``engine.stop()`` runs even if the tick task raises inside the group.

    PR #40 review finding: prior code placed ``engine.stop()`` outside
    the task-group block, so a tick-task exception bypassed it.
    """

    def crash() -> object:
        raise RuntimeError("simulated tick crash")

    monkeypatch.setattr(engine, "tick", crash)

    with pytest.raises(BaseException):
        async with tick_lifespan(engine, tick_hz=100.0):
            await anyio.sleep(0.5)

    assert engine.state.mode is Mode.SHUTDOWN, (
        f"engine.stop must run on tick-task crash, got mode={engine.state.mode}"
    )
