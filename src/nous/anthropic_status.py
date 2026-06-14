"""Anthropic call-cap surfacing (BL-021).

The Anthropic client (``anthropic_client.py``) enforces a file-locked
daily cap. The cap state is a controller-facing signal: a self-driving
session that has exhausted the cap must fall back to ``inference_local``
instead of issuing further cloud calls. This module pulls the cap
state out of :class:`~nous.anthropic_client.CallCap` and renders it as
a structured payload the MCP tool surface can return.

The structured payload is also the shape the
:class:`~nous.anthropic_client.CapExhausted` exception is rendered into
by :func:`cap_exhausted_payload`, so a controller that catches the
exception gets the same fields whether the cap exhaustion was
discovered by polling ``anthropic_cap_status`` or by a raised exception
inside ``inference_cloud``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .anthropic_client import CallCap, CapExhausted
from .config import Settings

__all__ = ["cap_exhausted_payload", "cap_status"]


def cap_status(settings: Settings, *, cap_path: Path | None = None) -> dict[str, Any]:
    """Return the structured Anthropic cap state for ``anthropic_cap_status``.

    The payload is JSON-safe and bounded: a controller can branch on
    ``exhausted`` to fall back to local inference, or read ``remaining``
    to spread calls across the rest of the UTC day. ``available`` is
    True only when the API key is configured and the cap has not been
    exhausted; ``cap=0`` is treated as "cap disabled" per the contract
    in ``CallCap.increment``.

    A corrupt on-disk counter is reported as ``corrupt: true`` with
    ``available: false`` and ``exhausted: true`` (audit CAP-1, ADR 0049):
    it is the state under which ``inference_cloud`` would refuse the cloud
    leg and fall back to the local mock, so the polled status must not
    advertise a healthy cap. ``count_today`` is ``null`` in that case
    because the real count is unknown until an operator repairs the file.
    """
    path = cap_path or (settings.home / ".anthropic_daily_count")
    reading = CallCap(path, settings.anthropic_daily_cap).peek()
    total = reading.cap
    api_key_configured = bool(_resolve_key(settings))
    if reading.corrupt:
        return {
            "available": False,
            "api_key_configured": api_key_configured,
            "cap": total,
            "count_today": None,
            "remaining": 0,
            "exhausted": True,
            "corrupt": True,
            "cap_disabled": total == 0,
            "model_default": settings.anthropic_model_default,
            "model_advanced": settings.anthropic_model_advanced,
        }
    count = reading.count
    exhausted = bool(total) and count >= total
    return {
        "available": api_key_configured and not exhausted,
        "api_key_configured": api_key_configured,
        "cap": total,
        "count_today": count,
        "remaining": max(0, total - count) if total else None,
        "exhausted": exhausted,
        "corrupt": False,
        "cap_disabled": total == 0,
        "model_default": settings.anthropic_model_default,
        "model_advanced": settings.anthropic_model_advanced,
    }


def cap_exhausted_payload(
    exc: CapExhausted, *, settings: Settings | None = None
) -> dict[str, Any]:
    """Render a :class:`CapExhausted` exception as a structured payload.

    ``inference_cloud`` (and any tool that calls
    :meth:`AnthropicClient.call` directly) can catch the exception and
    return this shape, letting the controller branch on ``reason`` and
    ``cap`` rather than parsing the exception's free-form message.
    """
    payload: dict[str, Any] = {
        "exhausted": True,
        "reason": str(exc),
        "kind": "cap_exhausted",
    }
    if settings is not None:
        snapshot = cap_status(settings)
        for field in ("cap", "count_today", "remaining", "cap_disabled"):
            payload[field] = snapshot[field]
    return payload


def _resolve_key(settings: Settings) -> str:
    import os

    if settings.anthropic_api_key is not None:
        return settings.anthropic_api_key.get_secret_value() or ""
    return os.environ.get("ANTHROPIC_API_KEY", "")
