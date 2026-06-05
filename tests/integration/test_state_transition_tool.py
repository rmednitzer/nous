"""The state_transition tool drives the mission-posture FSM (ADR 0031).

``build_app`` boots the engine (STOWED -> BOOT), so a fresh app parks in
BOOT exactly as the live server does. Before ADR 0031 the only registered
path out of BOOT was a ``scenario_inject`` action; the ``state_transition``
tool now exposes :meth:`Engine.request_transition` as a first-class T2
control surface.
"""

from __future__ import annotations

from collections.abc import Iterable

from nous.config import Settings
from nous.server import build_app


def _collect_text(result: Iterable[object]) -> str:
    text = ""
    for item in result:
        if isinstance(item, tuple) and len(item) == 2:
            text += str(item[1])
        elif hasattr(item, "text"):
            text += str(item.text)
        else:
            text += str(item)
    return text


async def test_state_transition_drives_boot_to_operational(config: Settings) -> None:
    app = build_app(config)
    start_mode = app.engine.state.mode.value
    assert start_mode == "boot"

    ready = _collect_text(
        await app.mcp.call_tool("state_transition", {"trigger": "ready"})
    )
    assert '"ok": true' in ready
    assert '"mode": "idle"' in ready

    # A safety-gated operational entry passes on a freshly-booted device
    # (full battery, junction well below the throttle threshold).
    mission = _collect_text(
        await app.mcp.call_tool("state_transition", {"trigger": "mission"})
    )
    assert '"ok": true' in mission
    assert '"mode": "mission"' in mission
    final_mode = app.engine.state.mode.value
    assert final_mode == "mission"


async def test_state_transition_reports_refusal_without_raising(
    config: Settings,
) -> None:
    app = build_app(config)
    # "mission" is not a table edge from BOOT: the tool returns ok=false
    # rather than surfacing the ValueError, and the posture is unchanged.
    text = _collect_text(
        await app.mcp.call_tool("state_transition", {"trigger": "mission"})
    )
    assert '"ok": false' in text
    held_mode = app.engine.state.mode.value
    assert held_mode == "boot"
