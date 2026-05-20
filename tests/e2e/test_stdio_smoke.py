"""End-to-end smoke: the FastMCP server exposes a non-empty tool list."""

from __future__ import annotations

import pytest

from nous.server import build_server


@pytest.mark.asyncio
async def test_server_lists_tools(tmp_nous_home: object) -> None:
    server = build_server()
    tools = await server.list_tools()
    names = [t.name for t in tools]
    assert names, "FastMCP should advertise at least the v0.1 representative tools"
    expected = {
        "device_info",
        "device_health",
        "state_get",
        "comms_state",
        "self_model_assess",
        "inference_local",
        "interop_formats",
    }
    assert expected.issubset(set(names)), f"missing tools: {expected - set(names)}"


@pytest.mark.asyncio
async def test_device_info_returns_json(tmp_nous_home: object) -> None:
    server = build_server()
    result = await server.call_tool("device_info", {})
    text = ""
    for item in result:
        if isinstance(item, tuple) and len(item) == 2:
            text += str(item[1])
        elif hasattr(item, "text"):
            text += str(item.text)
        else:
            text += str(item)
    assert "nous" in text
