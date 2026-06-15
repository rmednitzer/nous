"""The tick_advance tool steps simulated time deterministically (ADR 0040).

``build_app`` starts the engine but runs no tick loop, mirroring the
stateless HTTP deployment between requests; ``tick_advance`` is the
controller's way to move simulated time without waiting wall-clock.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from nous.config import Settings
from nous.server import build_app


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_tick_advance_steps_engine_time(config: Settings) -> None:
    app = build_app(config)
    before = app.engine.state.tick

    out = _payload(await app.mcp.call_tool("tick_advance", {"n": 5}))

    assert out["ok"] is True
    assert out["ticks_requested"] == 5
    # No background loop in this app, so the net engine advance equals the
    # ticks this call stepped.
    assert out["ticks_elapsed"] == 5
    assert out["tick"] == before + 5
    assert app.engine.state.tick == before + 5
    assert out["ts_s"] == pytest.approx(5 * app.engine.dt_s)
    assert out["mode"] == app.engine.state.mode.value


async def test_tick_advance_defaults_to_one(config: Settings) -> None:
    app = build_app(config)
    before = app.engine.state.tick

    out = _payload(await app.mcp.call_tool("tick_advance", {}))

    assert out["ok"] is True and out["ticks_requested"] == 1
    assert app.engine.state.tick == before + 1


async def test_tick_advance_bounds_are_enforced(config: Settings) -> None:
    app = build_app(config)
    before = app.engine.state.tick

    for n in (0, -3, 601):
        out = _payload(await app.mcp.call_tool("tick_advance", {"n": n}))
        assert out["ok"] is False
        assert "must be in [1, 600]" in out["error"]

    assert app.engine.state.tick == before
