"""Tests for the inference fallback ladder."""

from __future__ import annotations

import pytest

from nous.anthropic_client import CapExhausted, CapPersistError
from nous.inference_fallback import InferenceFallback
from nous.state.comms_state import CommsState


@pytest.mark.asyncio
async def test_cloud_used_when_comms_connected_and_cap_remaining() -> None:
    async def cloud(_p: str, _s: str) -> str:
        return "cloud response"

    async def local(_p: str) -> str:
        return "local response"

    f = InferenceFallback(
        cloud_call=cloud,
        local_call=local,
        comms_state=lambda: CommsState.CONNECTED,
        cap_remaining=lambda: 10,
    )
    result = await f.call("hi")
    assert result.path == "cloud"
    assert result.response == "cloud response"


@pytest.mark.asyncio
async def test_local_used_when_comms_degraded() -> None:
    async def cloud(_p: str, _s: str) -> str:
        return "cloud"

    async def local(_p: str) -> str:
        return "local-mock"

    f = InferenceFallback(
        cloud_call=cloud,
        local_call=local,
        comms_state=lambda: CommsState.DEGRADED,
        cap_remaining=lambda: 10,
    )
    result = await f.call("hi")
    assert result.path == "local_mock"
    assert "comms=degraded" in result.reason


@pytest.mark.asyncio
async def test_local_used_when_cap_exhausted() -> None:
    async def cloud(_p: str, _s: str) -> str:
        raise AssertionError("must not be called")

    async def local(_p: str) -> str:
        return "local-mock"

    f = InferenceFallback(
        cloud_call=cloud,
        local_call=local,
        comms_state=lambda: CommsState.CONNECTED,
        cap_remaining=lambda: 0,
    )
    result = await f.call("hi")
    assert result.path == "local_mock"
    assert "cap exhausted" in result.reason


@pytest.mark.asyncio
async def test_local_used_when_cloud_raises_cap_exhausted() -> None:
    async def cloud(_p: str, _s: str) -> str:
        raise CapExhausted("daily cap reached")

    async def local(_p: str) -> str:
        return "local-mock"

    f = InferenceFallback(
        cloud_call=cloud,
        local_call=local,
        comms_state=lambda: CommsState.CONNECTED,
        cap_remaining=lambda: 1,
    )
    result = await f.call("hi")
    assert result.path == "local_mock"
    assert "cap exhausted" in result.reason


@pytest.mark.asyncio
async def test_local_used_when_cloud_raises_cap_persist_error() -> None:
    # A durability fault (an fsync failure) is reported honestly as "cap not
    # persisted", not as exhaustion, while still failing closed to the mock
    # (ADR 0056).
    async def cloud(_p: str, _s: str) -> str:
        raise CapPersistError("counter could not be fsynced")

    async def local(_p: str) -> str:
        return "local-mock"

    f = InferenceFallback(
        cloud_call=cloud,
        local_call=local,
        comms_state=lambda: CommsState.CONNECTED,
        cap_remaining=lambda: 1,
    )
    result = await f.call("hi")
    assert result.path == "local_mock"
    assert "cap not persisted" in result.reason
    assert "cap exhausted" not in result.reason


@pytest.mark.asyncio
async def test_local_used_when_cloud_raises_other_exception() -> None:
    async def cloud(_p: str, _s: str) -> str:
        raise RuntimeError("network down")

    async def local(_p: str) -> str:
        return "local-mock"

    f = InferenceFallback(
        cloud_call=cloud,
        local_call=local,
        comms_state=lambda: CommsState.LIMITED,
        cap_remaining=lambda: 5,
    )
    result = await f.call("hi")
    assert result.path == "local_mock"
    assert "RuntimeError" in result.reason
