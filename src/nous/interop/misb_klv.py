"""MISB KLV (Key-Length-Value) adapter.

Encodes a small subset of MISB ST 0601 UAS LDS metadata as a KLV stream.

The keys are a single byte (MISB ST 0601 local set, range 1-255). The
length field uses BER short-form for values <128 bytes and BER long-form
for larger values. The encoder refuses both keys outside [1, 255] and
values larger than ``max_value_len`` (default 4 KiB) -- silent
truncation would corrupt downstream consumers.

A stamp timestamp (key 2, ``Unix Time Stamp``) is emitted on every
encode, satisfying SC-4's "include the source timestamp" half. The
encoder enforces ``max_age_s`` via :func:`assert_fresh`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import assert_fresh

__all__ = ["MisbKlvAdapter"]


_MISB_UAS_LDS_UNIVERSAL_KEY = bytes.fromhex("060E2B34020B01010E01030101000000")
_KEY_TIMESTAMP = 2
_DEFAULT_MAX_AGE_S = 30.0
_DEFAULT_MAX_VALUE_LEN = 4096
_BER_LONG_FORM_FLAG = 0x80


class MisbKlvAdapter:
    """BL-032. Encodes nous metadata into the MISB KLV byte stream."""

    name: str = "misb_klv"

    def __init__(
        self,
        *,
        max_age_s: float = _DEFAULT_MAX_AGE_S,
        max_value_len: int = _DEFAULT_MAX_VALUE_LEN,
    ) -> None:
        self.max_age_s = float(max_age_s)
        self.max_value_len = int(max_value_len)

    def encode(self, data: Mapping[str, Any]) -> bytes:
        ts_source = assert_fresh(self.name, data, max_age_s=self.max_age_s)
        items: list[tuple[int, bytes]] = [
            (_KEY_TIMESTAMP, int(ts_source * 1_000_000).to_bytes(8, "big", signed=False))
        ]
        for k, v in data.items():
            if k in ("ts", "ts_s"):
                continue
            if isinstance(k, int):
                key = k
            elif isinstance(k, str) and k.isdigit():
                key = int(k)
            else:
                continue
            if not 0 < key < 256 or key == _KEY_TIMESTAMP:
                raise ValueError(
                    f"misb_klv: key {key} out of range [1, 255] (or reserved)"
                )
            value = str(v).encode("utf-8")
            if len(value) > self.max_value_len:
                raise ValueError(
                    f"misb_klv: value for key {key} is {len(value)}B "
                    f"(max {self.max_value_len}B)"
                )
            items.append((key, value))
        body = b"".join(self._tlv(key, value) for key, value in items)
        return _MISB_UAS_LDS_UNIVERSAL_KEY + _ber_length(len(body)) + body

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        if not payload.startswith(_MISB_UAS_LDS_UNIVERSAL_KEY):
            return {"error": "misb_klv: missing UAS LDS universal key"}
        rest = payload[len(_MISB_UAS_LDS_UNIVERSAL_KEY) :]
        try:
            body_len, offset = _read_ber_length(rest)
        except ValueError as exc:
            return {"error": f"misb_klv: {exc}"}
        body = rest[offset : offset + body_len]
        if len(body) != body_len:
            return {"error": "misb_klv: truncated body"}
        items: dict[int, bytes] = {}
        i = 0
        while i < len(body):
            key = body[i]
            i += 1
            try:
                length, used = _read_ber_length(body[i:])
            except ValueError as exc:
                return {"error": f"misb_klv: {exc}"}
            i += used
            value = body[i : i + length]
            if len(value) != length:
                return {"error": "misb_klv: truncated TLV"}
            items[key] = value
            i += length
        return {"items": {k: v.hex() for k, v in items.items()}}

    @staticmethod
    def _tlv(key: int, value: bytes) -> bytes:
        return bytes([key]) + _ber_length(len(value)) + value


def _ber_length(length: int) -> bytes:
    if length < 0:
        raise ValueError("misb_klv: length must be non-negative")
    if length < 128:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    if len(encoded) > 0x7F:
        raise ValueError("misb_klv: BER length encoding overflow")
    return bytes([_BER_LONG_FORM_FLAG | len(encoded)]) + encoded


def _read_ber_length(buf: bytes) -> tuple[int, int]:
    if not buf:
        raise ValueError("missing length byte")
    first = buf[0]
    if first < 128:
        return first, 1
    num = first & 0x7F
    if num == 0 or num > len(buf) - 1:
        raise ValueError("malformed BER length")
    return int.from_bytes(buf[1 : 1 + num], "big"), 1 + num
