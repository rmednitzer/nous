"""The self_model_situation tool surfaces the fused situational read (ADR 0038).

``build_app`` boots the engine, so a fresh app has live estimator state to
fuse. The tool is a T0 read beside the other self-model reads; this pins that
it is registered and returns the fused shape (posture, capabilities with
provenance, safety posture, recommendations).
"""

from __future__ import annotations

import json
from typing import Any

from nous.config import Settings
from nous.server import build_app


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_situation_tool_is_registered_and_classified(config: Settings) -> None:
    app = build_app(config)
    names = {t.name for t in await app.mcp.list_tools()}
    assert "self_model_situation" in names


async def test_situation_tool_returns_fused_shape(config: Settings) -> None:
    app = build_app(config)
    app.engine.tick()
    out = _payload(await app.mcp.call_tool("self_model_situation", {}))

    assert {"tick", "ts_s", "posture", "capabilities", "safety", "recommendations"} <= (
        out.keys()
    )
    assert out["posture"]["mode"] == app.engine.state.mode.value
    assert out["recommendations"]
    names = {cap["name"] for cap in out["capabilities"]}
    assert "endurance_min" in names
    for cap in out["capabilities"]:
        assert cap["status"] in {"nominal", "watch", "degraded", "critical"}
        for prov in cap["provenance"]:
            assert prov["source"]
            assert prov["age_s"] >= 0.0
