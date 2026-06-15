"""EMCON tools and store-and-forward triage (BL-060 / ADR 0065).

The posture tools (``emcon_status`` / ``emcon_set``) drive the emission posture
through the MCP surface; the triage test drives the auto-enqueue-on-silence and
drain-on-lift cycle through a configured engine.
"""

from __future__ import annotations

import json
import time
from typing import Any

from nous.config import Settings
from nous.engine import Engine, _load_profile
from nous.server import build_app
from nous.tools.publish import encode_and_tx


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


def _emcon_profile(config: Settings) -> dict[str, Any]:
    profile = dict(_load_profile(config.profile))
    profile["comms"] = {
        "links": [
            {
                "id": "wifi",
                "bandwidth_bps": 1_000_000,
                "rssi_dbm_nominal": -55,
                "loss_pct_nominal": 0.1,
                "max_age_s": 30,
            },
        ],
        "outbox": {
            "enabled": True,
            "max_packages": 16,
            "max_bytes": 1_000_000,
            "default_ttl_s": 300,
        },
        "emcon": {"default": "unrestricted"},
    }
    return profile


async def test_emcon_status_defaults_to_unrestricted(config: Settings) -> None:
    app = build_app(config)
    out = _payload(await app.mcp.call_tool("emcon_status", {}))
    assert out["active"] == "unrestricted"
    assert "silent" in out["profiles"]


async def test_emcon_set_toggles_the_posture(config: Settings) -> None:
    app = build_app(config)
    silent = _payload(await app.mcp.call_tool("emcon_set", {"profile": "silent"}))
    assert silent["ok"] is True and silent["active"] == "silent"
    unknown = _payload(await app.mcp.call_tool("emcon_set", {"profile": "nope"}))
    assert unknown["ok"] is False and unknown["active"] == "silent"


async def test_comms_send_under_silence_reports_emcon(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    await app.mcp.call_tool("emcon_set", {"profile": "silent"})
    out = _payload(
        await app.mcp.call_tool("comms_send", {"link_id": link_id, "n_bytes": 1500})
    )
    assert out["ok"] is False
    assert out["reason"] == "emcon"
    assert out["bytes_accepted"] == 0


async def test_emcon_defer_keeps_link_health_and_skips_nonpositive(
    config: Settings,
) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    await app.mcp.call_tool("emcon_set", {"profile": "silent"})

    deferred = _payload(
        await app.mcp.call_tool("comms_send", {"link_id": link_id, "n_bytes": 1500})
    )
    assert deferred["reason"] == "emcon"
    link = app.engine.comms.link(link_id)
    assert link is not None
    assert deferred["connected"] == bool(link.is_live())

    zero = _payload(
        await app.mcp.call_tool("comms_send", {"link_id": link_id, "n_bytes": 0})
    )
    assert zero["ok"] is False
    assert zero["bytes_accepted"] == 0
    assert "reason" not in zero


def test_emcon_silence_defers_a_publish_then_drains(config: Settings) -> None:
    engine = Engine(settings=config, profile=_emcon_profile(config), seed=0)
    assert engine.comms.emcon.set_profile("silent") is True
    result = encode_and_tx(
        engine,
        "wifi",
        "cot",
        {"uid": "u", "ts_s": time.time(), "lat": 47.0, "lon": 13.0},
    )
    assert result["ok"] is False
    assert result["reason"] == "emcon"
    assert result["enqueued"] is True
    assert engine.outbox.depth() == 1

    # A flush while still silent cannot emit: the package stays held.
    held = engine.outbox.flush(engine.comms, now_s=engine.state.ts_s)
    assert len(held.delivered) == 0
    assert engine.outbox.depth() == 1

    # Lift EMCON and flush: the held package ships.
    engine.comms.emcon.set_profile("unrestricted")
    drained = engine.outbox.flush(engine.comms, now_s=engine.state.ts_s)
    assert len(drained.delivered) == 1
    assert engine.outbox.depth() == 0
