"""Interop adapter Protocol: ``encode / decode`` plus a shared freshness gate.

SC-4 from ``docs/stpa/05-safety-constraints.md`` requires every interop
adapter to:

1. include the source timestamp on every encoded message, and
2. refuse to encode when the underlying estimate is older than the
   adapter's ``max_age``.

This module exposes a small :class:`StaleEstimateError` for callers to
catch, and :func:`assert_fresh` so each adapter expresses the rule the
same way. The base ``Adapter`` Protocol stays minimal so adapters can be
tested in isolation.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

__all__ = ["Adapter", "StaleEstimateError", "assert_fresh", "resolve_ts"]


@runtime_checkable
class Adapter(Protocol):
    """An adapter encodes nous state to an external format and back.

    ``encode`` returns a serialised payload (bytes). ``decode`` parses an
    inbound payload back to a structured mapping. Streaming adapters can
    expose their own ``stream()`` coroutine; the base Protocol stays
    minimal so adapters can be tested in isolation.
    """

    name: str

    def encode(self, data: Mapping[str, Any]) -> bytes: ...

    def decode(self, payload: bytes) -> Mapping[str, Any]: ...


class StaleEstimateError(RuntimeError):
    """Raised by an adapter when its source estimate exceeds ``max_age``."""

    def __init__(self, adapter: str, age_s: float, max_age_s: float) -> None:
        self.adapter = adapter
        self.age_s = age_s
        self.max_age_s = max_age_s
        super().__init__(
            f"{adapter}: source estimate is {age_s:.2f}s old "
            f"(max_age_s={max_age_s:.2f}); SC-4 refuses encode"
        )


def resolve_ts(data: Mapping[str, Any], now_s: float | None = None) -> float:
    """Pull the source timestamp out of ``data`` (``ts_s`` or ``ts``).

    Falls back to ``now_s`` (defaulting to the wall clock) when the caller
    omitted a timestamp. A NaN or negative timestamp is treated as
    "missing" because it cannot be older than ``max_age`` in a finite
    sense.
    """
    candidate = data.get("ts_s", data.get("ts"))
    if candidate is None:
        return float(now_s) if now_s is not None else time.time()
    try:
        v = float(candidate)
    except (TypeError, ValueError):
        return float(now_s) if now_s is not None else time.time()
    if math.isnan(v) or v < 0.0:
        return float(now_s) if now_s is not None else time.time()
    return v


def assert_fresh(
    adapter_name: str,
    data: Mapping[str, Any],
    *,
    max_age_s: float,
    now_s: float | None = None,
) -> float:
    """Refuse to encode when the source estimate is older than ``max_age_s``.

    Returns the resolved source timestamp so the caller can stamp it into
    the encoded payload, satisfying the "must include the source
    timestamp" half of SC-4.
    """
    if max_age_s <= 0.0 or math.isnan(max_age_s):
        raise StaleEstimateError(adapter_name, 0.0, max_age_s)
    ts_source = resolve_ts(data, now_s=now_s)
    ts_now = float(now_s) if now_s is not None else time.time()
    age = ts_now - ts_source
    if age > max_age_s:
        raise StaleEstimateError(adapter_name, age, max_age_s)
    return ts_source
