"""The cloud-path inference tool inference_cloud (T2, ADR 0034).

inference_cloud wires the SC-5 fallback ladder (``nous.inference_fallback``)
over the existing capped Anthropic client (``nous.anthropic_client``) and the
local mock. These tests pin the tool's three observable outcomes -- cloud
served, degraded to the local mock with no key, and degraded on a raised
``CapExhausted`` -- without making a real API call. The cloud path is replaced
by a fake ``AnthropicClient.call`` so CI never reaches the network; the
no-key case relies on the autouse key-scrubbing fixture in ``conftest``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from nous.anthropic_client import AnthropicClient, CapExhausted
from nous.config import Settings
from nous.server import build_app
from nous.state.comms_state import CommsState


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_inference_cloud_degrades_to_local_without_key(config: Settings) -> None:
    app = build_app(config)
    out = _payload(await app.mcp.call_tool("inference_cloud", {"prompt": "status?"}))
    assert out["path"] == "local_mock"
    assert out["response"].startswith("[nous-local-mock")
    assert out["cap"]["api_key_configured"] is False


async def test_inference_cloud_uses_cloud_when_available(
    config: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = build_app(config)

    async def _fake_call(
        self: AnthropicClient,
        *,
        prompt: str,
        system: str,
        max_tokens: int = 1024,
        tier: str = "default",
    ) -> str:
        return f"CLOUD-OK::{prompt}"

    monkeypatch.setattr(AnthropicClient, "call", _fake_call)
    monkeypatch.setattr(
        app.engine.comms, "derive_state", lambda: (CommsState.CONNECTED, "test")
    )

    out = _payload(await app.mcp.call_tool("inference_cloud", {"prompt": "hello"}))
    assert out["path"] == "cloud"
    assert out["response"] == "CLOUD-OK::hello"
    assert out["cap_remaining"] is not None


async def test_inference_cloud_degrades_on_cap_exhausted(
    config: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = build_app(config)

    async def _raise_cap(
        self: AnthropicClient,
        *,
        prompt: str,
        system: str,
        max_tokens: int = 1024,
        tier: str = "default",
    ) -> str:
        raise CapExhausted("daily cap reached")

    monkeypatch.setattr(AnthropicClient, "call", _raise_cap)
    monkeypatch.setattr(
        app.engine.comms, "derive_state", lambda: (CommsState.CONNECTED, "test")
    )

    out = _payload(await app.mcp.call_tool("inference_cloud", {"prompt": "hi"}))
    assert out["path"] == "local_mock"
    assert "cap exhausted" in out["reason"]
    assert out["response"].startswith("[nous-local-mock")


async def test_inference_cloud_forwards_tier(
    config: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tool forwards a validated tier to the cloud call (BL-069)."""
    app = build_app(config)
    seen: dict[str, str] = {}

    async def _capture(
        self: AnthropicClient,
        *,
        prompt: str,
        system: str,
        max_tokens: int = 1024,
        tier: str = "default",
    ) -> str:
        seen["tier"] = tier
        return "CLOUD-OK"

    monkeypatch.setattr(AnthropicClient, "call", _capture)
    monkeypatch.setattr(
        app.engine.comms, "derive_state", lambda: (CommsState.CONNECTED, "test")
    )

    out = _payload(
        await app.mcp.call_tool(
            "inference_cloud", {"prompt": "deep question", "tier": "advanced"}
        )
    )
    assert out["path"] == "cloud"
    assert seen["tier"] == "advanced"
