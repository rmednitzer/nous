"""Scenario step injectors -- stub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["apply_injection"]


def apply_injection(action: str, args: Mapping[str, Any]) -> dict[str, Any]:
    """Translate a scenario step into an engine mutation.

    Returns a description of what would have been mutated; the L1
    implementation will actually mutate engine state (BL-014).
    """
    return {"action": action, "args": dict(args), "applied": False}
