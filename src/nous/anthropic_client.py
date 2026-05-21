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
    """File-locked daily call counter.

    Persistence layout is one JSON object on a single line. The file is
    opened with ``O_RDWR | O_CREAT`` (not ``O_APPEND``) so that
    ``seek(0); truncate(); write(...)`` is deterministic. Corrupted state
    refuses the call instead of silently resetting the counter -- a
    corrupted counter would otherwise defeat SC-5 by letting an attacker
    bypass the cap with a single bad write.
    """

    def __init__(self, path: Path, cap: int) -> None:
        self._path = path
        self._cap = cap

    def increment(self) -> tuple[int, int]:
        """Increment today's counter; return ``(count, cap)``.

        Raises :class:`CapExhausted` when today's count has reached the
        configured cap, or when the persisted counter is corrupt and
        cannot be safely recovered.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        fd = os.open(
            str(self._path),
            os.O_RDWR | os.O_CREAT,
            0o600,
        )
        try:
            fh = os.fdopen(fd, "r+", encoding="utf-8")
        except BaseException:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        with fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.seek(0)
                raw = fh.read().strip()
                state: dict[str, Any] = {"date": today, "count": 0}
                if raw:
                    try:
                        loaded = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise CapExhausted(
                            f"daily counter at {self._path} is corrupt: {exc}"
                        ) from exc
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
                fh.flush()
                with contextlib.suppress(OSError):
                    os.fsync(fh.fileno())
                return count + 1, self._cap
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def peek(self) -> tuple[int, int]:
        """Return ``(count_today, cap)`` without mutating the counter."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            raw = self._path.read_text(encoding="utf-8").strip()
        except OSError:
            return 0, self._cap
        if not raw:
            return 0, self._cap
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return 0, self._cap
        if not isinstance(state, dict) or state.get("date") != today:
            return 0, self._cap
        try:
            return int(state.get("count", 0)), self._cap
        except (TypeError, ValueError):
            return 0, self._cap


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
        timeout_s: float = 30.0,
    ) -> str:
        """Issue a Claude call, respecting the cap and the cache markers.

        ``timeout_s`` bounds the request at the SDK layer so a hung
        endpoint cannot stall the tick loop indefinitely. A timeout
        surfaces as the SDK's :class:`anthropic.APITimeoutError`, which
        the audited runner converts into a structured error line.
        """
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
            timeout=timeout_s,
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
