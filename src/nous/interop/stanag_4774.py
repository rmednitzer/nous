"""STANAG 4774/4778 confidentiality-label adapter -- stub."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

__all__ = ["Stanag4774Adapter"]


class Stanag4774Adapter:
    """BL-034. Wraps a payload in a STANAG 4774 confidentiality label."""

    name: str = "stanag_4774"

    def encode(self, data: Mapping[str, Any]) -> bytes:
        label = {
            "policyIdentifier": data.get("policy", "NATO"),
            "classification": data.get("classification", "UNCLASSIFIED"),
            "payload": data.get("payload", {}),
        }
        return json.dumps(label).encode("utf-8")

    def decode(self, payload: bytes) -> Mapping[str, Any]:
        try:
            obj = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return {"error": "invalid STANAG 4774 payload"}
        return obj if isinstance(obj, dict) else {"value": obj}
