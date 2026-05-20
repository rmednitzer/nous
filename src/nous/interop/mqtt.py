"""MQTT publish adapter -- stub."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

__all__ = ["MqttAdapter"]


class MqttAdapter:
    """BL-036. Publishes nous telemetry to an MQTT broker (paho)."""

    name: str = "mqtt"

    def __init__(self, broker: str = "localhost", port: int = 1883) -> None:
        self.broker = broker
        self.port = port

    def encode(self, data: Mapping[str, Any]) -> bytes:
        return json.dumps(dict(data)).encode("utf-8")

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        try:
            obj = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return {"error": "invalid MQTT payload"}
        return obj if isinstance(obj, dict) else {"value": obj}
