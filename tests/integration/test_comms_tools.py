"""The comms write tools comms_send / comms_publish (T2, ADR 0033).

comms_send wraps the comms subsystem's ``tx`` seam; comms_publish composes the
interop registry with ``tx`` so a controller can publish a standards-shaped
message on a named link and see its byte cost on the link envelope.
"""

from __future__ import annotations

import json
import time
from typing import Any

from nous.config import Settings
from nous.server import build_app


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_comms_send_records_transmission(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    out = _payload(
        await app.mcp.call_tool("comms_send", {"link_id": link_id, "n_bytes": 1500})
    )
    assert out["ok"] is True
    assert out["bytes_accepted"] == 1500
    assert out["connected"] is True


async def test_comms_send_rejects_unknown_link(config: Settings) -> None:
    app = build_app(config)
    out = _payload(
        await app.mcp.call_tool("comms_send", {"link_id": "no-such-link", "n_bytes": 100})
    )
    assert out["ok"] is False
    assert out["bytes_accepted"] == 0


async def test_comms_publish_encodes_and_transmits(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    out = _payload(
        await app.mcp.call_tool(
            "comms_publish",
            {
                "link_id": link_id,
                "adapter": "cot",
                "data": {"uid": "unit", "ts_s": time.time(), "lat": 47.0, "lon": 13.0},
            },
        )
    )
    assert out["ok"] is True
    assert out["adapter"] == "cot"
    assert out["len"] > 0
    # The encoded byte count is exactly what the link accounted for.
    assert out["bytes_accepted"] == out["len"]
    assert bytes.fromhex(out["payload_hex"]).startswith(b"<?xml")


async def test_comms_publish_unknown_adapter(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    out = _payload(
        await app.mcp.call_tool(
            "comms_publish",
            {"link_id": link_id, "adapter": "no-such-adapter", "data": {}},
        )
    )
    assert out["ok"] is False
    assert "error" in out


async def test_comms_publish_refuses_stale_estimate(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    out = _payload(
        await app.mcp.call_tool(
            "comms_publish",
            {
                "link_id": link_id,
                "adapter": "cot",
                "data": {"uid": "unit", "ts_s": 1.0, "lat": 0.0, "lon": 0.0},
            },
        )
    )
    assert out["ok"] is False
    assert out["error"] == "stale_estimate"
