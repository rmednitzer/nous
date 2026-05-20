"""Cursor-on-Target (CoT/TAK) adapter -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["CotAdapter"]


class CotAdapter:
    """BL-024. Encodes nous state to CoT XML and parses CoT XML back."""

    name: str = "cot"

    def encode(self, data: Mapping[str, Any]) -> bytes:
        uid = str(data.get("uid", "nous-unit"))
        lat = float(data.get("lat", 0.0))
        lon = float(data.get("lon", 0.0))
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<event version="2.0" uid="{uid}" type="a-f-G-U-C">'
            f'<point lat="{lat}" lon="{lon}" hae="0" ce="0" le="0"/>'
            f'</event>'
        ).encode()

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        return {"raw_len": len(payload), "note": "CoT decode lands with BL-024"}
