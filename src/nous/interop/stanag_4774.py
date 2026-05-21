"""STANAG 4774/4778 confidentiality-label adapter.

Wraps a payload in a STANAG 4774 confidentiality label. The encoder
includes the source timestamp and refuses to emit when the underlying
estimate is older than ``max_age_s`` (SC-4). The decoder bounds the input
size to ``max_payload_len`` (default 64 KiB) to prevent a malicious peer
from consuming memory with a single oversized payload.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .base import assert_fresh

__all__ = ["Stanag4774Adapter"]


_DEFAULT_MAX_AGE_S = 60.0
_DEFAULT_MAX_PAYLOAD_LEN = 64 * 1024


class Stanag4774Adapter:
    """BL-034. Wraps a payload in a STANAG 4774 confidentiality label."""

    name: str = "stanag_4774"

    def __init__(
        self,
        *,
        max_age_s: float = _DEFAULT_MAX_AGE_S,
        max_payload_len: int = _DEFAULT_MAX_PAYLOAD_LEN,
    ) -> None:
        self.max_age_s = float(max_age_s)
        self.max_payload_len = int(max_payload_len)

    def encode(self, data: Mapping[str, Any]) -> bytes:
        ts_source = assert_fresh(self.name, data, max_age_s=self.max_age_s)
        ts_iso = (
            datetime.fromtimestamp(ts_source, tz=UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        label = {
            "policyIdentifier": data.get("policy", "NATO"),
            "classification": data.get("classification", "UNCLASSIFIED"),
            "creationTime": ts_iso,
            "payload": data.get("payload", {}),
        }
        encoded = json.dumps(label).encode("utf-8")
        if len(encoded) > self.max_payload_len:
            raise ValueError(
                f"stanag_4774: encoded payload {len(encoded)}B "
                f"exceeds max_payload_len {self.max_payload_len}B"
            )
        return encoded

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        if len(payload) > self.max_payload_len:
            return {
                "error": (
                    f"stanag_4774: payload {len(payload)}B "
                    f"exceeds max_payload_len {self.max_payload_len}B"
                )
            }
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return {"error": f"invalid STANAG 4774 payload: {exc}"}
        return obj if isinstance(obj, dict) else {"value": obj}
