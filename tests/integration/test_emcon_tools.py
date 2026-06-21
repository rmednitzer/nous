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
from nous.server import Nous, build_app
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


def _emcon_app(config: Settings, emcon: dict[str, Any]) -> Nous:
    """Build the MCP app, then swap its engine for one under a custom EMCON profile.

    The tools read ``app.engine`` dynamically, so the real wrappers (audit, JSON
    shape, ``now_s`` injection, the ``_publish_shape`` step) drive against the
    posture rather than a hand-rolled ``encode_and_tx`` / ``outbox.flush`` call,
    closing the BL-105 MCP-path coverage gap.
    """
    profile = dict(_load_profile(config.profile))
    profile["comms"] = {
        "links": [
            {
                "id": "lte",
                "bandwidth_bps": 1_000_000,
                "rssi_dbm_nominal": -75,
                "loss_pct_nominal": 0.0,
                "max_age_s": 600,
            },
        ],
        "outbox": {
            "enabled": True,
            "max_packages": 16,
            "max_bytes": 1_000_000,
            "default_ttl_s": 600,
        },
        "emcon": emcon,
    }
    app = build_app(config)
    app.engine.stop()
    app.engine = Engine(settings=config, profile=profile, seed=0)
    app.engine.start()
    return app


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
    # A non-positive send is rejected outright, not deferred to the outbox: it now
    # carries a failure reason (BL-109) but no enqueue, unlike the byte-bearing
    # EMCON defer above which adds `enqueued`.
    assert "enqueued" not in zero
    assert "reason" in zero


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


def test_emcon_window_holds_a_send_then_drains_when_the_burst_opens(
    config: Settings,
) -> None:
    profile = dict(_load_profile(config.profile))
    profile["comms"] = {
        "links": [
            {
                "id": "lte",
                "bandwidth_bps": 1_000_000,
                "rssi_dbm_nominal": -75,
                "loss_pct_nominal": 0.0,
                "max_age_s": 300,
            },
        ],
        "outbox": {
            "enabled": True,
            "max_packages": 16,
            "max_bytes": 1_000_000,
            "default_ttl_s": 600,
        },
        "emcon": {
            "default": "burst",
            "profiles": {
                "burst": {
                    "permit_links": ["lte"],
                    "window": {"period_s": 100, "on_s": 1, "phase_s": 50},
                }
            },
        },
    }
    engine = Engine(settings=config, profile=profile, seed=0)
    assert engine.comms.emcon.active == "burst"
    # ts_s == 0 sits between bursts (the window opens at 50), so the send is held.
    assert engine.comms.emcon.permits("lte", now_s=engine.state.ts_s) is False
    result = encode_and_tx(
        engine,
        "lte",
        "cot",
        {"uid": "u", "ts_s": time.time(), "lat": 47.0, "lon": 13.0},
    )
    assert result["ok"] is False
    assert result["reason"] == "emcon"
    assert result["enqueued"] is True
    assert engine.outbox.depth() == 1

    # A flush still between bursts cannot emit: the package stays held.
    held = engine.outbox.flush(engine.comms, now_s=0.0)
    assert len(held.delivered) == 0
    assert engine.outbox.depth() == 1

    # A flush inside the open burst ships it.
    drained = engine.outbox.flush(engine.comms, now_s=50.0)
    assert len(drained.delivered) == 1
    assert engine.outbox.depth() == 0


async def test_emcon_status_includes_window_fields(config: Settings) -> None:
    app = build_app(config)
    out = _payload(await app.mcp.call_tool("emcon_status", {}))
    assert out["emitting"] is True
    assert out["window"] is None
    assert "windows" in out


def test_publish_under_minimizing_posture_coarsens_position(config: Settings) -> None:
    from nous.interop import build_adapter

    profile = dict(_load_profile(config.profile))
    profile["comms"] = {
        "links": [
            {
                "id": "lte",
                "bandwidth_bps": 1_000_000,
                "rssi_dbm_nominal": -75,
                "loss_pct_nominal": 0.0,
                "max_age_s": 300,
            },
        ],
        "outbox": {
            "enabled": True,
            "max_packages": 16,
            "max_bytes": 1_000_000,
            "default_ttl_s": 300,
        },
        "emcon": {
            "default": "low_pi",
            "profiles": {
                "low_pi": {"permit_links": ["lte"], "minimize": {"position_decimals": 2}}
            },
        },
    }
    engine = Engine(settings=config, profile=profile, seed=0)
    ts = time.time()
    result = encode_and_tx(
        engine,
        "lte",
        "cot",
        {"uid": "u", "ts_s": ts, "lat": 47.123456, "lon": 13.654321},
    )
    assert result["ok"] is True
    # The emitted wire form is the encoding of the coarsened mapping, not the
    # full-precision input: position is rounded to the configured two decimals.
    expected = build_adapter("cot").encode(
        {"uid": "u", "ts_s": ts, "lat": 47.12, "lon": 13.65}
    )
    assert bytes.fromhex(result["payload_hex"]) == expected


# -- BL-105: drive the publish / flush MCP tools under each EMCON posture --


async def test_comms_publish_under_silence_defers_then_flush_drains(
    config: Settings,
) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    await app.mcp.call_tool("emcon_set", {"profile": "silent"})

    published = _payload(
        await app.mcp.call_tool(
            "comms_publish",
            {
                "link_id": link_id,
                "adapter": "cot",
                "data": {"uid": "u", "ts_s": time.time(), "lat": 47.0, "lon": 13.0},
            },
        )
    )
    assert published["ok"] is False
    assert published["reason"] == "emcon"
    assert published["enqueued"] is True

    # A flush while still silent cannot emit: the tool injects the engine clock
    # as now_s and the EMCON gate denies, so the package stays held.
    held = _payload(await app.mcp.call_tool("comms_flush", {}))
    assert held["delivered_count"] == 0
    assert held["depth"] == 1

    # Lift EMCON and flush: the held package ships through the MCP tool path.
    await app.mcp.call_tool("emcon_set", {"profile": "unrestricted"})
    drained = _payload(await app.mcp.call_tool("comms_flush", {}))
    assert drained["delivered_count"] == 1
    assert drained["depth"] == 0


async def test_self_model_publish_under_silence_defers(config: Settings) -> None:
    app = build_app(config)
    link_id = app.engine.comms.link_ids[0]
    await app.mcp.call_tool("emcon_set", {"profile": "silent"})
    out = _payload(
        await app.mcp.call_tool(
            "self_model_publish",
            {"link_id": link_id, "adapter": "mqtt", "kind": "situation"},
        )
    )
    assert out["ok"] is False
    assert out["reason"] == "emcon"
    assert out["enqueued"] is True
    assert out["kind"] == "situation"
    read = _payload(await app.mcp.call_tool("comms_outbox", {}))
    assert read["depth"] == 1


async def test_comms_publish_under_a_window_holds_then_drains_on_the_burst(
    config: Settings,
) -> None:
    app = _emcon_app(
        config,
        {
            "default": "burst",
            "profiles": {
                "burst": {
                    "permit_links": ["lte"],
                    "window": {"period_s": 100, "on_s": 50, "phase_s": 20},
                }
            },
        },
    )
    assert app.engine.comms.emcon.active == "burst"
    assert app.engine.state.ts_s == 0.0  # between bursts (the window opens at 20)

    published = _payload(
        await app.mcp.call_tool(
            "comms_publish",
            {
                "link_id": "lte",
                "adapter": "cot",
                "data": {"uid": "u", "ts_s": time.time(), "lat": 47.0, "lon": 13.0},
            },
        )
    )
    assert published["ok"] is False
    assert published["reason"] == "emcon"
    assert published["enqueued"] is True

    # comms_flush at ts_s=0 is still between bursts: the injected now_s is closed.
    held = _payload(await app.mcp.call_tool("comms_flush", {}))
    assert held["delivered_count"] == 0
    assert held["depth"] == 1

    # Advance the sim clock into the open burst; the tick loop drains the held
    # package once the window injects an open now_s.
    await app.mcp.call_tool("tick_advance", {"n": 80})  # ts_s -> 40, inside [20, 70)
    assert 20.0 <= app.engine.state.ts_s < 70.0
    drained = _payload(await app.mcp.call_tool("comms_outbox", {}))
    assert drained["depth"] == 0


async def test_comms_publish_under_a_minimizing_posture_coarsens_position(
    config: Settings,
) -> None:
    from nous.interop import build_adapter

    app = _emcon_app(
        config,
        {
            "default": "low_pi",
            "profiles": {
                "low_pi": {
                    "permit_links": ["lte"],
                    "minimize": {"position_decimals": 2},
                }
            },
        },
    )
    ts = time.time()
    published = _payload(
        await app.mcp.call_tool(
            "comms_publish",
            {
                "link_id": "lte",
                "adapter": "cot",
                "data": {"uid": "u", "ts_s": ts, "lat": 47.123456, "lon": 13.654321},
            },
        )
    )
    assert published["ok"] is True
    # The emitted wire form is the encoding of the coarsened mapping (position
    # rounded to two decimals), produced inside the comms_publish tool path.
    expected = build_adapter("cot").encode(
        {"uid": "u", "ts_s": ts, "lat": 47.12, "lon": 13.65}
    )
    assert bytes.fromhex(published["payload_hex"]) == expected
