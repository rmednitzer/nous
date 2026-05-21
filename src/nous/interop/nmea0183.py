"""NMEA 0183 adapter.

Emits a conformant ``$GPGGA`` sentence: lat/lon are formatted as
DDMM.mmmm with explicit hemisphere indicators, the timestamp is
``HHMMSS.ss`` UTC, and the checksum is the XOR of every byte between
``$`` and ``*`` (NMEA 0183 4.10, section 5.3). The encoder enforces
SC-4: a stale source estimate raises :class:`StaleEstimateError`.

The decoder validates the checksum and refuses sentences that do not
start with ``$``. Non-ASCII input is rejected: NMEA 0183 is strict
US-ASCII over the wire and a sentence carrying any other byte is, by
definition, malformed and must not be accepted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .base import assert_fresh

__all__ = ["Nmea0183Adapter"]


_DEFAULT_MAX_AGE_S = 5.0


class Nmea0183Adapter:
    """BL-033. Emits and parses GGA sentences."""

    name: str = "nmea0183"

    def __init__(self, *, max_age_s: float = _DEFAULT_MAX_AGE_S) -> None:
        self.max_age_s = float(max_age_s)

    def encode(self, data: Mapping[str, Any]) -> bytes:
        ts_source = assert_fresh(self.name, data, max_age_s=self.max_age_s)
        lat = float(data.get("lat", 0.0))
        lon = float(data.get("lon", 0.0))
        if math.isnan(lat) or math.isnan(lon):
            raise ValueError("NMEA0183: lat/lon must be finite")
        if not -90.0 <= lat <= 90.0:
            raise ValueError(f"NMEA0183: lat {lat} outside [-90, 90]")
        if not -180.0 <= lon <= 180.0:
            raise ValueError(f"NMEA0183: lon {lon} outside [-180, 180]")
        alt_m = float(data.get("alt_m", 0.0))
        sats = int(data.get("satellites", 8))
        hdop = float(data.get("hdop", 0.9))
        fix_quality = int(data.get("fix_quality", 1))
        hh_mm_ss = datetime.fromtimestamp(ts_source, tz=UTC).strftime("%H%M%S.00")
        lat_str, lat_hemi = _format_lat(lat)
        lon_str, lon_hemi = _format_lon(lon)
        body = (
            f"GPGGA,{hh_mm_ss},{lat_str},{lat_hemi},{lon_str},{lon_hemi},"
            f"{fix_quality},{sats:02d},{hdop:.1f},{alt_m:.1f},M,0.0,M,,"
        )
        if not body.isascii():
            raise ValueError("NMEA0183: payload must be 7-bit ASCII")
        checksum = 0
        for ch in body.encode("ascii"):
            checksum ^= ch
        return f"${body}*{checksum:02X}\r\n".encode("ascii")

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        try:
            text = payload.decode("ascii")
        except UnicodeDecodeError:
            return {"error": "NMEA0183: non-ASCII payload"}
        text = text.strip()
        if not text.startswith("$"):
            return {"error": "NMEA0183: missing '$' sentence start"}
        if "*" not in text:
            return {"error": "NMEA0183: missing checksum delimiter"}
        body, _, suffix = text[1:].partition("*")
        suffix = suffix.strip()
        if len(suffix) < 2:
            return {"error": "NMEA0183: checksum field too short"}
        try:
            received = int(suffix[:2], 16)
        except ValueError:
            return {"error": "NMEA0183: checksum is not hex"}
        computed = 0
        for ch in body.encode("ascii"):
            computed ^= ch
        if computed != received:
            return {
                "error": (
                    f"NMEA0183: checksum mismatch "
                    f"(computed=0x{computed:02X}, received=0x{received:02X})"
                )
            }
        fields = body.split(",")
        return {"talker": fields[0][:2], "type": fields[0][2:], "fields": fields[1:]}


def _format_lat(lat: float) -> tuple[str, str]:
    hemi = "N" if lat >= 0.0 else "S"
    deg = int(abs(lat))
    minutes = (abs(lat) - deg) * 60.0
    return f"{deg:02d}{minutes:07.4f}", hemi


def _format_lon(lon: float) -> tuple[str, str]:
    hemi = "E" if lon >= 0.0 else "W"
    deg = int(abs(lon))
    minutes = (abs(lon) - deg) * 60.0
    return f"{deg:03d}{minutes:07.4f}", hemi
