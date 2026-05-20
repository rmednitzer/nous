"""Cached Anthropic client with a daily call cap and prompt-cache discipline.

The simulator's ``inference_cloud`` tool funnels every Claude call through
this module. Three behaviours are intentional:

1. **Daily cap.** A file-locked counter at ``$NOUS_HOME/.anthropic_daily_count``
   bounds calls per UTC day. When the cap is exhausted every further call
   raises :class:`CapExhausted` and the caller is expected to fall back to
   ``inference_local`` (the local mock).
2. **Prompt caching.** The system prompt and any RAG/tool-result content are
   marked with ``cache_control`` so repeated calls within the cache TTL pay
   only the input-token discount.
3. **Slot discipline.** Untrusted content (sensor text, intercepted radio
   payloads) is always placed in the *user* message slot. The system slot
   and tool-result slots are reserved for trusted content.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import TextBlockParam

from .config import Settings, get_settings

__all__ = ["AnthropicClient", "CallCap", "CapExhausted", "build_client"]


class CapExhausted(RuntimeError):
    """Raised when the daily Anthropic call cap is exhausted."""


class CallCap:
    """File-locked daily call counter."""

    def __init__(self, path: Path, cap: int) -> None:
        self._path = path
        self._cap = cap

    def increment(self) -> tuple[int, int]:
        """Increment today's counter; return ``(count, cap)``. Raises ``CapExhausted``."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        with self._path.open("a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.seek(0)
                raw = fh.read().strip()
                state: dict[str, Any] = {"date": today, "count": 0}
                if raw:
                    with contextlib.suppress(json.JSONDecodeError):
                        loaded = json.loads(raw)
                        if isinstance(loaded, dict):
                            state = loaded
                if state.get("date") != today:
                    state = {"date": today, "count": 0}
                count = int(state.get("count", 0))
                if self._cap and count >= self._cap:
                    raise CapExhausted(
                        f"daily Anthropic call cap reached ({count}/{self._cap})"
                    )
                state["count"] = count + 1
                fh.seek(0)
                fh.truncate()
                fh.write(json.dumps(state))
                return count + 1, self._cap
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class AnthropicClient:
    """Thin wrapper that enforces the cap and prompt-cache discipline."""

    def __init__(self, settings: Settings, cap_path: Path | None = None) -> None:
        self.settings = settings
        api_key = (
            settings.anthropic_api_key.get_secret_value()
            if settings.anthropic_api_key
            else os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self._client = AsyncAnthropic(api_key=api_key) if api_key else None
        self._cap = CallCap(
            cap_path or (settings.home / ".anthropic_daily_count"),
            settings.anthropic_daily_cap,
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    async def call(
        self,
        *,
        prompt: str,
        system: str,
        model: str | None = None,
        max_tokens: int = 1024,
        trusted_context: Iterable[Mapping[str, Any]] = (),
    ) -> str:
        """Issue a Claude call, respecting the cap and the cache markers."""
        if self._client is None:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        self._cap.increment()
        sys_blocks: list[TextBlockParam] = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        for block in trusted_context:
            sys_blocks.append(
                {
                    "type": "text",
                    "text": json.dumps(dict(block), default=str),
                    "cache_control": {"type": "ephemeral"},
                }
            )
        response = await self._client.messages.create(
            model=model or self.settings.anthropic_model_default,
            max_tokens=max_tokens,
            system=sys_blocks,
            messages=[{"role": "user", "content": prompt}],
        )
        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", "")
            if text:
                parts.append(text)
        return "\n".join(parts)


@lru_cache(maxsize=1)
def build_client() -> AnthropicClient:
    """Process-wide cached Anthropic client."""
    return AnthropicClient(get_settings())
