"""The self_model_publish tool pushes the self-model over a link (ADR 0041).

The publish target settled by the ADR is the composition ``comms_publish``
established: shape for an interop adapter, encode to wire bytes, account
the bytes on a comms link. These tests decode the returned ``payload_hex``
back through the same adapters to assert the wire form really carries the
self-model read.
"""

from __future__ import annotations

import json
from typing import Any

from nous.config import Settings
from nous.interop import CotAdapter
from nous.server import build_app


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_publish_situation_over_mqtt(config: Settings) -> None:
    app = build_app(config)
    app.engine.tick()

    out = _payload(
        await app.mcp.call_tool(
            "self_model_publish",
            {"link_id": "lte", "adapter": "mqtt", "kind": "situation"},
        )
    )

    assert out["ok"] is True
    assert out["bytes_accepted"] == out["len"] > 0
    wire = json.loads(bytes.fromhex(out["payload_hex"]).decode("utf-8"))
    assert wire["kind"] == "self_model_situation"
    assert "ts" in wire  # SC-4: the envelope carries the source timestamp
    body = wire["self_model"]
    assert body["posture"]["mode"] == app.engine.state.mode.value
    assert {c["name"] for c in body["capabilities"]} == {
        "endurance_min",
        "thermal_headroom_c",
        "inference_capacity_tok_per_s",
        "perception_range_m",
    }


async def test_publish_assess_over_sensorthings(config: Settings) -> None:
    app = build_app(config)
    app.engine.tick()

    out = _payload(
        await app.mcp.call_tool(
            "self_model_publish",
            {"link_id": "tak", "adapter": "sensorthings", "kind": "assess"},
        )
    )

    assert out["ok"] is True
    wire = json.loads(bytes.fromhex(out["payload_hex"]).decode("utf-8"))
    assert wire["Datastream"]["name"] == "nous-self_model_assess"
    assert "endurance_min" in wire["result"]["capabilities"]
    assert wire["result"]["explanation"]


async def test_publish_over_cot_carries_position_and_remarks(
    config: Settings,
) -> None:
    app = build_app(config)
    app.engine.tick()

    out = _payload(
        await app.mcp.call_tool(
            "self_model_publish",
            {"link_id": "tak", "adapter": "cot", "kind": "situation"},
        )
    )

    assert out["ok"] is True
    wire = bytes.fromhex(out["payload_hex"])
    decoded = dict(CotAdapter().decode(wire))
    assert decoded["uid"] == "nous-self-model"
    # The decoder only lifts the event/point attributes; the capability
    # summary rides the <remarks> detail in the wire form itself.
    assert "endurance_min=" in wire.decode("utf-8")


async def test_position_codecs_are_refused(config: Settings) -> None:
    app = build_app(config)

    for adapter in ("nmea0183", "misb_klv"):
        out = _payload(
            await app.mcp.call_tool(
                "self_model_publish", {"link_id": "lte", "adapter": adapter}
            )
        )
        assert out["ok"] is False
        assert "no payload channel" in out["error"]


async def test_unknown_adapter_kind_and_link_are_refused(config: Settings) -> None:
    app = build_app(config)

    unknown_adapter = _payload(
        await app.mcp.call_tool(
            "self_model_publish", {"link_id": "lte", "adapter": "carrier-pigeon"}
        )
    )
    assert unknown_adapter["ok"] is False

    unknown_kind = _payload(
        await app.mcp.call_tool(
            "self_model_publish",
            {"link_id": "lte", "adapter": "mqtt", "kind": "vibes"},
        )
    )
    assert unknown_kind["ok"] is False
    assert "unknown kind" in unknown_kind["error"]

    unknown_link = _payload(
        await app.mcp.call_tool(
            "self_model_publish", {"link_id": "carrier-pigeon", "adapter": "mqtt"}
        )
    )
    assert unknown_link["ok"] is False
    assert unknown_link["bytes_accepted"] == 0
