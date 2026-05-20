"""OGC SensorThings adapter -- stub."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

__all__ = ["SensorThingsAdapter"]


class SensorThingsAdapter:
    """BL-025. Emits Observations / Datastreams in the SensorThings JSON shape."""

    name: str = "sensorthings"

    def encode(self, data: Mapping[str, Any]) -> bytes:
        envelope = {
            "@iot.id": data.get("id", 0),
            "result": data.get("result", None),
            "phenomenonTime": data.get("ts", None),
            "Datastream": {"name": data.get("datastream", "nous")},
        }
        return json.dumps(envelope).encode("utf-8")

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        try:
            obj = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return {"error": "invalid SensorThings JSON"}
        return obj if isinstance(obj, dict) else {"value": obj}
