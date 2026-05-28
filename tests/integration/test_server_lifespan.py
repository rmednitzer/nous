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
async def test_build_app_exposes_engine_and_mcp(tmp_nous_home: object) -> None:
    """``build_app`` returns the engine and FastMCP; ``build_server`` the latter."""
    from mcp.server.fastmcp import FastMCP

    from nous.server import build_app

    app = build_app()
    assert isinstance(app.engine, Engine)
    assert isinstance(app.mcp, FastMCP)
    # Back-compatible accessor still returns just the FastMCP tool surface.
    assert isinstance(build_server(), FastMCP)


@pytest.mark.asyncio
async def test_attach_tick_lifespan_ticks_for_process(engine: Engine) -> None:
    """The tick loop runs for the app (process) lifespan, not per request.

    ADR 0024: under ``stateless_http`` the low-level MCP server runs once
    per request, so a server-lifespan tick loop would reboot the engine on
    every call. ``attach_tick_lifespan`` composes the tick loop onto the
    Starlette app lifespan instead, so ticks accumulate continuously for
    the whole lifespan and the engine stops exactly once on exit.
    """
    from starlette.applications import Starlette

    from nous.server import attach_tick_lifespan

    app = Starlette()
    attach_tick_lifespan(app, engine, tick_hz=100.0)
    initial = engine.state.tick
    async with app.router.lifespan_context(app):
        await anyio.sleep(0.1)
        ticked = engine.state.tick - initial
    assert ticked >= 5, f"expected continuous ticking over the lifespan, got {ticked}"
    assert engine.state.mode is Mode.SHUTDOWN, "engine should stop once on exit"


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

    with pytest.raises(ExceptionGroup) as excinfo:
        async with tick_lifespan(engine, tick_hz=100.0):
            await anyio.sleep(0.5)

    runtime_errors = [
        exc for exc in excinfo.value.exceptions if isinstance(exc, RuntimeError)
    ]
    assert any("simulated tick crash" in str(exc) for exc in runtime_errors), (
        f"expected the simulated tick crash inside the group, "
        f"got exceptions={excinfo.value.exceptions!r}"
    )
    assert engine.state.mode is Mode.SHUTDOWN, (
        f"engine.stop must run on tick-task crash, got mode={engine.state.mode}"
    )
