"""Internal vocabulary for the comms-stack state (ADR-0006)."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from ..types import LinkEstimate

__all__ = ["CommsState", "derive"]

# A link is rate-healthy when its sustainable capacity clears this fraction of
# its own rated bandwidth (BL-048, ADR 0053). This per-link comparison replaces
# the flat threshold across a heterogeneous link inventory (a 50 kbps LoRa link
# and a 20 Mbps LTE link no longer share one absolute floor).
_CAPACITY_HEALTHY_FRACTION = 0.25
# Legacy absolute floor, used only for an estimate that carries no bandwidth (a
# bare test fixture); a real subsystem link always reports its bandwidth.
_LEGACY_THROUGHPUT_FLOOR_BPS = 5_000.0


class CommsState(StrEnum):
    CONNECTED = "connected"
    LIMITED = "limited"
    DEGRADED = "degraded"
    DENIED = "denied"


def _rate_healthy(link: LinkEstimate) -> bool:
    if link.bandwidth_bps > 0.0:
        return link.capacity_bps > _CAPACITY_HEALTHY_FRACTION * link.bandwidth_bps
    return link.throughput_bps > _LEGACY_THROUGHPUT_FLOOR_BPS


def derive(links: Iterable[LinkEstimate]) -> tuple[CommsState, str]:
    """Summarise an iterable of link estimates into a single state label."""
    links = list(links)
    if not links:
        return CommsState.DENIED, "no links present"
    connected = [link for link in links if link.connected]
    if not connected:
        return CommsState.DENIED, "no link is connected"
    healthy = [
        link for link in connected if link.loss_pct < 5.0 and _rate_healthy(link)
    ]
    if len(healthy) == len(links):
        return CommsState.CONNECTED, "all links healthy"
    if not healthy:
        return CommsState.DEGRADED, "no link is healthy"
    return CommsState.LIMITED, "at least one link is degraded"
