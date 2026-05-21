"""OGC SensorThings adapter.

Emits Observations in the OGC SensorThings JSON shape. ``phenomenonTime``
is stamped from the source estimate timestamp, enforcing SC-4's
"include the source timestamp" rule. The encoder refuses to emit when
the underlying estimate is older than ``max_age_s``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .base import assert_fresh

__all__ = ["SensorThingsAdapter"]


_DEFAULT_MAX_AGE_S = 60.0
_DEFAULT_MAX_PAYLOAD_LEN = 64 * 1024


class SensorThingsAdapter:
    """BL-025. Emits Observations / Datastreams in the SensorThings JSON shape."""

    name: str = "sensorthings"

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
        phenomenon_time = (
            datetime.fromtimestamp(ts_source, tz=UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        envelope = {
            "@iot.id": data.get("id", 0),
            "result": data.get("result", None),
            "phenomenonTime": phenomenon_time,
            "resultTime": phenomenon_time,
            "Datastream": {"name": data.get("datastream", "nous")},
        }
        encoded = json.dumps(envelope).encode("utf-8")
        if len(encoded) > self.max_payload_len:
            raise ValueError(
                f"sensorthings: encoded payload {len(encoded)}B "
                f"exceeds max_payload_len {self.max_payload_len}B"
            )
        return encoded

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        if len(payload) > self.max_payload_len:
            return {
                "error": (
                    f"sensorthings: payload {len(payload)}B "
                    f"exceeds max_payload_len {self.max_payload_len}B"
                )
            }
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return {"error": f"invalid SensorThings JSON: {exc}"}
        return obj if isinstance(obj, dict) else {"value": obj}
