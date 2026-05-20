"""MISB KLV (Key-Length-Value) adapter -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["MisbKlvAdapter"]


class MisbKlvAdapter:
    """BL-032. Encodes nous metadata into the MISB KLV byte stream."""

    name: str = "misb_klv"

    def encode(self, data: Mapping[str, Any]) -> bytes:
        return b"".join(
            self._tlv(int(k), str(v).encode("utf-8"))
            for k, v in data.items()
            if isinstance(k, int) or (isinstance(k, str) and k.isdigit())
        )

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        return {"raw_len": len(payload), "note": "KLV decode lands with BL-032"}

    @staticmethod
    def _tlv(key: int, value: bytes) -> bytes:
        return bytes([key & 0xFF, len(value) & 0xFF]) + value
