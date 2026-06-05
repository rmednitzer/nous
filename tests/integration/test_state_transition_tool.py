"""The state_transition tool drives the mission-posture FSM (ADR 0031).

``build_app`` boots the engine (STOWED -> BOOT), so a fresh app parks in
BOOT exactly as the live server does. Before ADR 0031 the only registered
path out of BOOT was a ``scenario_inject`` action; the ``state_transition``
tool now exposes :meth:`Engine.request_transition` as a first-class T2
control surface.
"""

from __future__ import annotations

import json
from typing import Any

from nous.config import Settings
from nous.server import build_app


def _payload(result: Any) -> dict[str, Any]:
    """Parse the tool's JSON return out of the FastMCP call result.

    ``call_tool`` returns ``(content, structured)``; the tool returns a JSON
    string, so the first content block's ``text`` is the object we assert on.
    """
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_state_transition_drives_boot_to_operational(config: Settings) -> None:
    app = build_app(config)
    assert app.engine.state.mode.value == "boot"

    ready = _payload(await app.mcp.call_tool("state_transition", {"trigger": "ready"}))
    assert ready["ok"] is True
    assert ready["mode"] == "idle"

    # A safety-gated operational entry passes on a freshly-booted device
    # (full battery, junction well below the throttle threshold).
    mission = _payload(await app.mcp.call_tool("state_transition", {"trigger": "mission"}))
    assert mission["ok"] is True
    assert mission["mode"] == "mission"
    assert app.engine.state.mode.value == "mission"


async def test_state_transition_reports_refusal_without_raising(
    config: Settings,
) -> None:
    app = build_app(config)
    # "mission" is not a table edge from BOOT: the tool returns ok=false
    # rather than surfacing the ValueError, and the posture is unchanged.
    out = _payload(await app.mcp.call_tool("state_transition", {"trigger": "mission"}))
    assert out["ok"] is False
    assert app.engine.state.mode.value == "boot"


async def test_state_transition_refuses_terminal_triggers(config: Settings) -> None:
    app = build_app(config)
    # fault and shutdown reach the reset-only terminal modes; the T2 tool
    # refuses them (they belong to the T3 state_force_* tools) and leaves the
    # posture unchanged.
    for trigger in ("fault", "shutdown"):
        out = _payload(await app.mcp.call_tool("state_transition", {"trigger": trigger}))
        assert out["ok"] is False
        assert "terminal" in str(out["reason"])
        assert app.engine.state.mode.value == "boot"
