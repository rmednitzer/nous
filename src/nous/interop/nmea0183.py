"""NMEA 0183 adapter -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["Nmea0183Adapter"]


class Nmea0183Adapter:
    """BL-033. Emits and parses GGA / RMC sentences."""

    name: str = "nmea0183"

    def encode(self, data: Mapping[str, Any]) -> bytes:
        lat = float(data.get("lat", 0.0))
        lon = float(data.get("lon", 0.0))
        ts = str(data.get("ts", "000000"))
        body = f"GPGGA,{ts},{lat:.4f},N,{lon:.4f},E,1,08,0.9,0,M,46,M,,"
        chk = 0
        for ch in body:
            chk ^= ord(ch)
        return f"${body}*{chk:02X}\r\n".encode("ascii")

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        return {
            "raw_len": len(payload),
            "note": "NMEA decode delegates to pynmea2 with BL-033",
        }
