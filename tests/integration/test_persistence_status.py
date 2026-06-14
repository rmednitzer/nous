"""device_info surfaces transition-log persistence health (AUDIT-2026-06-14 DB-1).

A failed ``init_db`` at server start used to be swallowed silently, leaving the
state-transition history memory-only with no signal anywhere. ``device_info``
now carries a ``persistence`` block so an operator sees a degraded sink instead
of discovering it from an empty ``state_history``.
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


async def test_device_info_reports_healthy_persistence(config: Settings) -> None:
    app = build_app(config)
    info = _payload(await app.mcp.call_tool("device_info", {}))
    assert "persistence" in info
    assert info["persistence"]["persistent"] is True
    assert info["persistence"]["degraded"] is False


async def test_device_info_surfaces_failed_db_init(
    config: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        # A connection-time message can carry the DB URL and its credentials.
        raise OSError("could not connect to postgresql://nous:s3cret@db.internal/state")

    monkeypatch.setattr("nous.server.init_db", _boom)
    app = build_app(config)

    # The engine still came up (the failure is swallowed so the device ticks).
    assert app.engine.state.tick >= 0
    info = _payload(await app.mcp.call_tool("device_info", {}))
    persistence = info["persistence"]
    assert persistence["persistent"] is False
    assert persistence["degraded"] is True
    # Only the exception class is surfaced; the message (and any credentials it
    # carries) must not leak through the T0 device_info read.
    assert persistence["init_error"] == "OSError"
    assert "s3cret" not in json.dumps(info)
