"""The `eoir_status` tool: envelope read and target-block null-safety.

When a target is set but the terrain / position seams are not wired (a profile
with no world), the subsystem reports the line-of-sight fields as None. The tool
must stay inert in that configuration rather than rounding None (PR #173 review).
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


async def test_eoir_status_reports_the_envelope(config: Settings) -> None:
    app = build_app(config)
    out = _payload(await app.mcp.call_tool("eoir_status", {}))
    assert "eo_range_m" in out
    assert "ir_range_m" in out
    assert "estimate" in out
    assert "target" not in out  # no target configured


async def test_eoir_status_omits_target_block_without_seams(config: Settings) -> None:
    # The default profile has no world, so terrain is unwired; setting a target
    # must not make the tool round() a None slant / confidence.
    app = build_app(config)
    app.engine.eoir.set_target(bearing_deg=90.0, range_m=4000.0, height_m=1.0)
    out = _payload(await app.mcp.call_tool("eoir_status", {}))
    assert "target" not in out
    assert "eo_range_m" in out  # the envelope is still reported
