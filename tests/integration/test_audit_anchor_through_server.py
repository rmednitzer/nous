"""The FastMCP server wires the daily audit anchor (BL-031, ADR 0026).

A tool call advances the audit chain and then drives ``maybe_anchor``, so
the first call of a UTC day writes one anchor; ``audit_anchor_verify`` then
cross-checks it against the chain and ``device_info`` advertises the anchor
path.
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


async def test_tool_call_writes_daily_anchor(config: Settings) -> None:
    app = build_app(config)
    anchor_path = config.resolved_anchor_path()
    assert not anchor_path.exists()

    # The first tool call writes an audit record, then drives maybe_anchor.
    await app.mcp.call_tool("device_info", {})
    assert anchor_path.exists()
    assert len(anchor_path.read_text(encoding="utf-8").strip().splitlines()) == 1

    # A second call the same UTC day does not write a duplicate anchor.
    await app.mcp.call_tool("device_health", {})
    assert len(anchor_path.read_text(encoding="utf-8").strip().splitlines()) == 1


async def test_audit_anchor_verify_tool_reports_ok(config: Settings) -> None:
    app = build_app(config)
    await app.mcp.call_tool("device_info", {})

    result = await app.mcp.call_tool("audit_anchor_verify", {})
    text = _collect_text(result)
    assert '"ok": true' in text
    assert '"anchors": 1' in text
    assert '"checked": 1' in text


async def test_device_info_advertises_anchor_path(config: Settings) -> None:
    app = build_app(config)
    result = await app.mcp.call_tool("device_info", {})
    text = _collect_text(result)
    assert '"anchor_path"' in text
    assert str(config.resolved_anchor_path()) in text
