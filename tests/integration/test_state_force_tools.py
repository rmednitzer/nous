"""The T3 terminal-control tools state_force_fault / state_force_shutdown (ADR 0032).

These are the irreversible counterparts to the T2 ``state_transition`` tool,
which refuses the terminal ``fault`` / ``shutdown`` triggers and points the
controller here. ``build_app`` boots the engine to BOOT, so the lifecycle below
starts where the live server does.
"""

from __future__ import annotations

import json
from typing import Any

from nous.config import Settings
from nous.server import build_app


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_state_force_fault_from_operational(config: Settings) -> None:
    app = build_app(config)
    await app.mcp.call_tool("state_transition", {"trigger": "ready"})
    await app.mcp.call_tool("state_transition", {"trigger": "mission"})

    out = _payload(await app.mcp.call_tool("state_force_fault", {}))
    assert out["ok"] is True
    assert out["mode"] == "fault"
    assert app.engine.state.mode.value == "fault"


async def test_state_force_shutdown_from_idle(config: Settings) -> None:
    app = build_app(config)
    await app.mcp.call_tool("state_transition", {"trigger": "ready"})

    out = _payload(await app.mcp.call_tool("state_force_shutdown", {}))
    assert out["ok"] is True
    assert out["mode"] == "shutdown"
    assert app.engine.state.mode.value == "shutdown"


async def test_state_force_fault_refused_from_terminal(config: Settings) -> None:
    app = build_app(config)
    # Reach a terminal mode, then a second terminal trigger has no table edge
    # and is reported as ok=false rather than raising.
    await app.mcp.call_tool("state_force_shutdown", {})  # BOOT -> SHUTDOWN
    out = _payload(await app.mcp.call_tool("state_force_fault", {}))
    assert out["ok"] is False
    assert out["mode"] == "shutdown"


async def test_terminal_recovery_via_state_transition(config: Settings) -> None:
    app = build_app(config)
    # The T3 tool drives into FAULT; recovery is the deliberate T2 path
    # reset -> STOWED -> boot, since STOWED is not terminal.
    await app.mcp.call_tool("state_transition", {"trigger": "ready"})
    fault = _payload(await app.mcp.call_tool("state_force_fault", {}))
    assert fault["mode"] == "fault"

    reset = _payload(await app.mcp.call_tool("state_transition", {"trigger": "reset"}))
    assert reset["ok"] is True
    assert reset["mode"] == "stowed"

    boot = _payload(await app.mcp.call_tool("state_transition", {"trigger": "boot"}))
    assert boot["ok"] is True
    assert boot["mode"] == "boot"
