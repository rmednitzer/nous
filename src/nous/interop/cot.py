"""Cursor-on-Target (CoT/TAK) adapter.

CoT 2.0 requires ``time``, ``start``, and ``stale`` attributes on every
``<event>``. The adapter enforces SC-4: the source estimate timestamp is
stamped into the message and the encoder refuses to emit when the
estimate is older than ``max_age_s`` (default 60 s per the LTE / TAK link
budgets in ``profiles/jetson-agx-orin.yaml``).

The adapter escapes every interpolated string with ``xml.sax.saxutils``
so an operator name or unit identifier carrying ``<``, ``>``, or ``&``
cannot break out of an attribute and inject a sibling element.

Decoding is intentionally narrow: it pulls canonical attributes off the
root ``event`` element using ``xml.etree.ElementTree`` and explicitly
refuses payloads containing ``DOCTYPE`` or ``ENTITY`` declarations. That
keeps the adapter safe from XXE attacks if the controller ever decodes a
payload from an untrusted peer.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from xml.etree import ElementTree  # nosec B405 - XXE-safe via _safe_parse + DOCTYPE refusal
from xml.sax.saxutils import escape, quoteattr  # nosec B406 - output escape, not input parser

from .base import assert_fresh

__all__ = ["CotAdapter"]


_DEFAULT_MAX_AGE_S = 60.0
_DEFAULT_STALE_S = 120.0


class CotAdapter:
    """BL-024. Encodes nous state to CoT XML and parses CoT XML back."""

    name: str = "cot"

    def __init__(
        self,
        *,
        max_age_s: float = _DEFAULT_MAX_AGE_S,
        stale_s: float = _DEFAULT_STALE_S,
    ) -> None:
        self.max_age_s = float(max_age_s)
        self.stale_s = float(stale_s)

    def encode(self, data: Mapping[str, Any]) -> bytes:
        ts_source = assert_fresh(self.name, data, max_age_s=self.max_age_s)
        uid = str(data.get("uid", "nous-unit"))
        type_attr = str(data.get("type", "a-f-G-U-C"))
        lat = float(data.get("lat", 0.0))
        lon = float(data.get("lon", 0.0))
        hae = float(data.get("hae", 0.0))
        ce = float(data.get("ce", 9999999.0))
        le = float(data.get("le", 9999999.0))
        ts = datetime.fromtimestamp(ts_source, tz=UTC)
        start = ts.isoformat(timespec="seconds").replace("+00:00", "Z")
        stale = (
            (ts + timedelta(seconds=self.stale_s))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f"<event version=\"2.0\" uid={quoteattr(uid)} "
            f"type={quoteattr(type_attr)} "
            f"time=\"{start}\" start=\"{start}\" stale=\"{stale}\" "
            f"how=\"m-g\">"
            f"<point lat=\"{lat:.7f}\" lon=\"{lon:.7f}\" "
            f"hae=\"{hae:.2f}\" ce=\"{ce:.2f}\" le=\"{le:.2f}\"/>"
            f"<detail><contact callsign={quoteattr(str(data.get('callsign', uid)))}/>"
            f"<remarks>{escape(str(data.get('remarks', '')))}</remarks></detail>"
            f"</event>"
        ).encode()

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        try:
            root = _safe_parse(payload)
        except ElementTree.ParseError as exc:
            return {"error": f"invalid CoT XML: {exc}"}
        if root is None or root.tag != "event":
            return {"error": "missing <event> root"}
        out: dict[str, Any] = {
            "uid": root.attrib.get("uid", ""),
            "type": root.attrib.get("type", ""),
            "time": root.attrib.get("time", ""),
            "start": root.attrib.get("start", ""),
            "stale": root.attrib.get("stale", ""),
        }
        point = root.find("point")
        if point is not None:
            for key in ("lat", "lon", "hae", "ce", "le"):
                raw = point.attrib.get(key)
                if raw is None:
                    continue
                try:
                    out[key] = float(raw)
                except ValueError:
                    out[key] = raw
        return out


def _safe_parse(payload: bytes) -> ElementTree.Element | None:
    """Parse CoT XML without resolving external entities (XXE-safe)."""
    parser = ElementTree.XMLParser()  # nosec B314 - explicit DOCTYPE / ENTITY refusal below
    # ``ElementTree`` does not resolve external entities by default in
    # CPython, but we explicitly assert no doctype so a controller that
    # someday swaps in a different parser cannot regress quietly.
    if b"<!DOCTYPE" in payload[:512] or b"<!ENTITY" in payload[:512]:
        raise ElementTree.ParseError("DOCTYPE / ENTITY declarations refused")
    parser.feed(payload)
    return parser.close()
