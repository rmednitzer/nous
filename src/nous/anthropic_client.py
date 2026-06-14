"""Cached Anthropic client with a daily call cap and prompt-cache discipline.

The simulator's ``inference_cloud`` tool funnels every Claude call through
this module. Four behaviours are intentional:

1. **Daily cap.** A file-locked counter at ``$NOUS_HOME/.anthropic_daily_count``
   bounds calls per UTC day. When the cap is exhausted every further call
   raises :class:`CapExhausted` and the caller is expected to fall back to
   ``inference_local`` (the local mock).
2. **Prompt caching.** The system prompt and any RAG/tool-result content are
   marked with ``cache_control`` so repeated calls within the cache TTL pay
   only the input-token discount. The response's ``cache_read_input_tokens``
   is recorded on :attr:`AnthropicClient.last_cache_read_input_tokens` so the
   discipline is observable rather than assumed.
3. **Slot discipline.** Untrusted content (sensor text, intercepted radio
   payloads) is always placed in the *user* message slot. The system slot
   and tool-result slots are reserved for trusted content.
4. **Enriched call (BL-069, ADR 0035).** ``call`` selects a model tier
   (default / advanced), enables adaptive thinking on the thinking-capable
   tier, and streams long generations through ``messages.stream`` so a slow
   response stays inside the request timeout. The default tier is unchanged.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from anthropic import AsyncAnthropic, Omit, omit
from anthropic.types import (
    Message,
    TextBlockParam,
    ThinkingConfigAdaptiveParam,
    ThinkingConfigParam,
)

from .config import Settings, get_settings

__all__ = [
    "AnthropicClient",
    "CallCap",
    "CapExhausted",
    "CapReading",
    "build_client",
]

_ADAPTIVE_THINKING: ThinkingConfigAdaptiveParam = {"type": "adaptive"}

# Stream a generation longer than this so a slow cloud response stays inside the
# request timeout instead of tripping the SDK's non-streaming guard (the
# claude-api skill: stream for long output / high max_tokens).
_STREAM_OVER_TOKENS = 1024

# Model families that accept ``thinking={"type": "adaptive"}``. Haiku 4.5 (the
# default tier) does not, so the call omits the block there rather than 400 the
# request; only a thinking-capable tier (Sonnet 4.6, Opus 4.6+) gains it.
_THINKING_CAPABLE_PREFIXES = (
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-4-6",
)


def _supports_adaptive_thinking(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in _THINKING_CAPABLE_PREFIXES)


def _join_text(message: Message) -> str:
    """Concatenate the text blocks, dropping any adaptive-thinking block."""
    parts: list[str] = []
    for block in message.content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts)


class CapExhausted(RuntimeError):
    """Raised when the daily Anthropic call cap is exhausted."""


class _CorruptCounter(Exception):
    """Internal: the persisted daily counter cannot be safely parsed.

    Both :meth:`CallCap.increment` (the spend path) and :meth:`CallCap.peek`
    (the status path) route the on-disk line through :func:`_parse_count`, so
    this exception is the single point at which "the counter is unusable" is
    decided. Increment converts it into :class:`CapExhausted` and refuses the
    call; peek reports it as a corrupt reading. They cannot drift (audit
    CAP-1, ADR 0049).
    """


def _parse_count(raw: str, today: str) -> int:
    """Return today's call count from one persisted JSON line.

    Returns ``0`` for the cases :meth:`CallCap.increment` treats as a fresh
    day: an empty line, valid JSON that is not an object, or a line whose
    ``date`` is not ``today``. Raises :class:`_CorruptCounter` for the cases
    increment must refuse rather than silently reset, since a corrupt counter
    would otherwise let an attacker bypass the cap with one bad write (SC-5):
    non-JSON, or a ``count`` that is not integer-coercible.
    """
    if not raw:
        return 0
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _CorruptCounter(str(exc)) from exc
    if not isinstance(loaded, dict) or loaded.get("date") != today:
        return 0
    try:
        return int(loaded.get("count", 0))
    except (TypeError, ValueError) as exc:
        raise _CorruptCounter(f"non-integer count: {loaded.get('count')!r}") from exc


@dataclass(frozen=True, slots=True)
class CapReading:
    """A non-mutating read of the daily counter.

    ``corrupt`` is ``True`` when the persisted counter cannot be parsed, the
    same condition under which :meth:`CallCap.increment` refuses the call.
    A corrupt counter is reported as exhausted by ``anthropic_cap_status`` so
    the polled status never advertises a slot the spend path would deny.
    """

    count: int
    cap: int
    corrupt: bool = False


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
                try:
                    count = _parse_count(raw, today)
                except _CorruptCounter as exc:
                    raise CapExhausted(
                        f"daily counter at {self._path} is corrupt: {exc}"
                    ) from exc
                if self._cap and count >= self._cap:
                    raise CapExhausted(
                        f"daily Anthropic call cap reached ({count}/{self._cap})"
                    )
                new_count = count + 1
                fh.seek(0)
                fh.truncate()
                fh.write(json.dumps({"date": today, "count": new_count}))
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError as exc:
                    raise CapExhausted(
                        f"daily counter at {self._path} could not be fsynced: {exc}"
                    ) from exc
                return new_count, self._cap
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def peek(self) -> CapReading:
        """Return a non-mutating :class:`CapReading` of today's counter.

        A corrupt counter is reported as ``corrupt`` rather than as a fresh
        ``count=0``: it is exactly the state under which :meth:`increment`
        refuses the call, so a polled status must not advertise a slot the
        spend path would deny (audit CAP-1, ADR 0049). The parse goes through
        the same :func:`_parse_count` that increment uses, so the two cannot
        disagree.
        """
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            raw = self._path.read_text(encoding="utf-8").strip()
        except OSError:
            return CapReading(count=0, cap=self._cap)
        try:
            return CapReading(count=_parse_count(raw, today), cap=self._cap)
        except _CorruptCounter:
            return CapReading(count=0, cap=self._cap, corrupt=True)


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
        self.last_cache_read_input_tokens: int | None = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def _resolve_model(self, tier: str, model: str | None) -> str:
        if model is not None:
            return model
        if tier == "advanced":
            return self.settings.anthropic_model_advanced
        return self.settings.anthropic_model_default

    async def call(
        self,
        *,
        prompt: str,
        system: str,
        tier: Literal["default", "advanced"] = "default",
        model: str | None = None,
        max_tokens: int = 1024,
        thinking: bool = True,
        trusted_context: Iterable[Mapping[str, Any]] = (),
        timeout_s: float = 30.0,
    ) -> str:
        """Issue a Claude call, respecting the cap and the cache markers.

        ``tier`` selects ``anthropic_model_default`` ("default") or
        ``anthropic_model_advanced`` ("advanced"); an explicit ``model``
        overrides both. ``thinking`` requests adaptive thinking, but it is
        only sent when the resolved model supports it (BL-069 / ADR 0035), so
        the default Haiku tier never receives a block it would reject. A
        generation above ``_STREAM_OVER_TOKENS`` is streamed and collected
        with ``get_final_message`` so a long response stays inside the
        timeout. ``timeout_s`` bounds the request at the SDK layer so a hung
        endpoint cannot stall the tick loop indefinitely; a timeout surfaces
        as the SDK's :class:`anthropic.APITimeoutError`, which the audited
        runner converts into a structured error line.
        """
        if self._client is None:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        self._cap.increment()
        resolved = self._resolve_model(tier, model)
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
        thinking_param: ThinkingConfigParam | Omit = (
            _ADAPTIVE_THINKING
            if thinking and _supports_adaptive_thinking(resolved)
            else omit
        )
        client = self._client.with_options(timeout=timeout_s)
        messages: list[Any] = [{"role": "user", "content": prompt}]
        message: Message
        if max_tokens > _STREAM_OVER_TOKENS:
            async with client.messages.stream(
                model=resolved,
                max_tokens=max_tokens,
                system=sys_blocks,
                messages=messages,
                thinking=thinking_param,
            ) as stream:
                message = await stream.get_final_message()
        else:
            message = await client.messages.create(
                model=resolved,
                max_tokens=max_tokens,
                system=sys_blocks,
                messages=messages,
                thinking=thinking_param,
            )
        self.last_cache_read_input_tokens = message.usage.cache_read_input_tokens
        return _join_text(message)


@lru_cache(maxsize=1)
def build_client() -> AnthropicClient:
    """Process-wide cached Anthropic client."""
    return AnthropicClient(get_settings())
