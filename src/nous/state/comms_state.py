"""Internal vocabulary for the comms-stack state (ADR-0006)."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from ..types import LinkEstimate

__all__ = ["CommsState", "derive"]


class CommsState(StrEnum):
    CONNECTED = "connected"
    LIMITED = "limited"
    DEGRADED = "degraded"
    DENIED = "denied"


def derive(links: Iterable[LinkEstimate]) -> tuple[CommsState, str]:
    """Summarise an iterable of link estimates into a single state label."""
    links = list(links)
    if not links:
        return CommsState.DENIED, "no links present"
    connected = [link for link in links if link.connected]
    if not connected:
        return CommsState.DENIED, "no link is connected"
    healthy = [
        link for link in connected if link.loss_pct < 5.0 and link.throughput_bps > 5_000
    ]
    if len(healthy) == len(links):
        return CommsState.CONNECTED, "all links healthy"
    if not healthy:
        return CommsState.DEGRADED, "no link is healthy"
    return CommsState.LIMITED, "at least one link is degraded"
