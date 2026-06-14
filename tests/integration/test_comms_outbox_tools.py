"""The store-and-forward outbox tools and the tick-driven drain (BL-077, ADR 0047).

comms_enqueue holds a package when comms cannot carry it; comms_outbox reads the
triage queue; comms_flush forces a drain. The engine tick drains the outbox
automatically as links recover, so a package queued during a denied-comms window
survives instead of being dropped the way comms_publish drops it.
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


async def test_enqueue_then_outbox_read(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    out = _payload(
        await app.mcp.call_tool(
            "comms_enqueue",
            {"link_id": link_id, "n_bytes": 512, "precedence": "immediate"},
        )
    )
    assert out["ok"] is True
    assert out["depth"] == 1

    read = _payload(await app.mcp.call_tool("comms_outbox", {}))
    assert read["depth"] == 1
    assert read["queued_bytes"] == 512
    assert read["by_precedence"]["immediate"] == 1
    assert read["head"]["precedence"] == "immediate"
    assert read["counters"]["enqueued"] == 1
    assert len(read["packages"]) == 1


async def test_enqueue_accepts_payload_hex(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    out = _payload(
        await app.mcp.call_tool(
            "comms_enqueue",
            {"link_id": link_id, "payload_hex": "deadbeef", "kind": "cot"},
        )
    )
    assert out["ok"] is True
    assert out["package"]["size_bytes"] == 4
    assert out["package"]["kind"] == "cot"


async def test_enqueue_rejects_bad_hex(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    out = _payload(
        await app.mcp.call_tool(
            "comms_enqueue",
            {"link_id": link_id, "payload_hex": "nothex!!"},
        )
    )
    assert out["ok"] is False
    assert "hex" in out["reason"]


async def test_enqueue_requires_size_or_payload(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    out = _payload(
        await app.mcp.call_tool("comms_enqueue", {"link_id": link_id})
    )
    assert out["ok"] is False
    assert "n_bytes or payload_hex" in out["reason"]


async def test_flush_delivers_on_live_link(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    await app.mcp.call_tool(
        "comms_enqueue", {"link_id": link_id, "n_bytes": 256, "precedence": "flash"}
    )
    out = _payload(await app.mcp.call_tool("comms_flush", {}))
    assert out["ok"] is True
    assert out["delivered_count"] == 1
    assert out["depth"] == 0


async def test_flush_link_filter_leaves_other_links_queued(config: Settings) -> None:
    app = build_app(config)
    links = app.engine.comms.link_ids
    assert len(links) >= 2
    await app.mcp.call_tool("comms_enqueue", {"link_id": links[0], "n_bytes": 100})
    await app.mcp.call_tool("comms_enqueue", {"link_id": links[1], "n_bytes": 100})

    out = _payload(await app.mcp.call_tool("comms_flush", {"link_id": links[0]}))
    assert out["delivered_count"] == 1
    assert out["depth"] == 1  # the other link's package is untouched


async def test_outbox_drains_on_tick_after_recovery(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    app.engine.comms.set_link_state(link_id, connected=False)

    enq = _payload(
        await app.mcp.call_tool(
            "comms_enqueue",
            {"link_id": link_id, "n_bytes": 300, "precedence": "immediate"},
        )
    )
    assert enq["ok"] is True

    app.engine.tick()  # link still down -> package deferred, not delivered
    assert app.engine.outbox.depth() == 1
    assert app.engine.outbox.delivered_total == 0

    app.engine.comms.clear_link_override(link_id)  # link recovers
    app.engine.tick()  # tick-driven drain delivers it

    read = _payload(await app.mcp.call_tool("comms_outbox", {}))
    assert read["depth"] == 0
    assert read["counters"]["delivered"] == 1


async def test_enqueue_survives_what_publish_would_drop(config: Settings) -> None:
    """The fix in one test: a down link drops a publish but holds an enqueue."""
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    app.engine.comms.set_link_state(link_id, connected=False)

    published = _payload(
        await app.mcp.call_tool(
            "comms_publish",
            {
                "link_id": link_id,
                "adapter": "cot",
                "data": {"uid": "probe", "ts_s": time.time(), "lat": 1.0, "lon": 2.0},
            },
        )
    )
    # comms_publish encodes but the down link accepts nothing: the message is gone.
    assert published["ok"] is False
    assert published["bytes_accepted"] == 0

    queued = _payload(
        await app.mcp.call_tool(
            "comms_enqueue",
            {"link_id": link_id, "n_bytes": published["len"], "precedence": "priority"},
        )
    )
    assert queued["ok"] is True
    assert app.engine.outbox.depth() == 1  # held, not dropped


async def test_outbox_tools_are_audited(config: Settings) -> None:
    """comms_enqueue/flush are T2 and comms_outbox is T0: all three are audited."""
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    await app.mcp.call_tool("comms_enqueue", {"link_id": link_id, "n_bytes": 64})
    await app.mcp.call_tool("comms_outbox", {})
    await app.mcp.call_tool("comms_flush", {})

    summary = _payload(await app.mcp.call_tool("audit_summary", {}))
    assert summary["writes_total"] >= 3
