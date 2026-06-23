"""The `self_estimator_status` tool surfaces every live estimator's health.

A controller asking for estimator health must see all of them; the EO/IR Kalman
was previously omitted from the iteration even though the engine constructs,
ticks, and finiteness-checks it (2026-06-23 audit). Pin the full set so a future
estimator addition is not silently dropped from the read.
"""

from __future__ import annotations

import json
from typing import Any

from nous.config import Settings
from nous.server import build_app


def _payload(result: Any) -> Any:
    content, _structured = result
    return json.loads(content[0].text)


async def test_self_estimator_status_includes_every_estimator(config: Settings) -> None:
    app = build_app(config)
    rows = _payload(await app.mcp.call_tool("self_estimator_status", {}))["estimators"]
    sources = {row["source"] for row in rows}
    expected = {
        "power",
        "apu",
        "thermal",
        "compute",
        "storage",
        "comms",
        "position",
        "sensors",
        "eoir",
        "biometrics",
    }
    # Exact equality, not subset: a new estimator omitted from the tool must fail
    # here, not slip through. (The dynamic engine-derived pin lives in the
    # regression suite, `TestAudit20260623SelfEstimatorStatusCoversEoir`.)
    assert sources == expected, (
        f"missing: {expected - sources}; unexpected: {sources - expected}"
    )


async def test_self_estimator_status_surfaces_eoir_health(config: Settings) -> None:
    app = build_app(config)
    rows = _payload(await app.mcp.call_tool("self_estimator_status", {}))["estimators"]
    eoir = next(row for row in rows if row["source"] == "eoir")
    assert "point" in eoir and "covariance" in eoir
    assert "health" in eoir
