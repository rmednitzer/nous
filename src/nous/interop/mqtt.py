"""MQTT publish adapter.

Stamps every encoded envelope with the source estimate timestamp and
refuses to encode when the underlying estimate is older than
``max_age_s`` (SC-4). The decoder bounds input to ``max_payload_len`` to
prevent broker amplification attacks.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .base import assert_fresh

__all__ = ["MqttAdapter"]


_DEFAULT_MAX_AGE_S = 30.0
_DEFAULT_MAX_PAYLOAD_LEN = 64 * 1024


class MqttAdapter:
    """BL-036. Publishes nous telemetry to an MQTT broker (paho)."""

    name: str = "mqtt"

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        *,
        max_age_s: float = _DEFAULT_MAX_AGE_S,
        max_payload_len: int = _DEFAULT_MAX_PAYLOAD_LEN,
    ) -> None:
        self.broker = broker
        self.port = port
        self.max_age_s = float(max_age_s)
        self.max_payload_len = int(max_payload_len)

    def encode(self, data: Mapping[str, Any]) -> bytes:
        ts_source = assert_fresh(self.name, data, max_age_s=self.max_age_s)
        ts_iso = (
            datetime.fromtimestamp(ts_source, tz=UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        envelope: dict[str, Any] = dict(data)
        envelope.setdefault("ts", ts_iso)
        encoded = json.dumps(envelope).encode("utf-8")
        if len(encoded) > self.max_payload_len:
            raise ValueError(
                f"mqtt: encoded payload {len(encoded)}B "
                f"exceeds max_payload_len {self.max_payload_len}B"
            )
        return encoded

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        if len(payload) > self.max_payload_len:
            return {
                "error": (
                    f"mqtt: payload {len(payload)}B "
                    f"exceeds max_payload_len {self.max_payload_len}B"
                )
            }
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return {"error": f"invalid MQTT payload: {exc}"}
        return obj if isinstance(obj, dict) else {"value": obj}
