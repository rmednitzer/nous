"""Comms estimator: per-link belief over connectivity + RSSI.

A minimal scalar estimator that wraps the comms subsystem's
per-link observations into :class:`~nous.types.LinkEstimate`
instances and exposes the count of live links as the aggregate
:class:`~nous.types.Estimate` point. The full particle filter over
connectivity transitions lives in BL-030; this estimator is the
plumbing the controller and self-model layer rely on today.
"""

from __future__ import annotations

import math

from ..types import Estimate, LinkEstimate, Observation

__all__ = ["CommsParticleFilter"]


_LIVE_THROUGHPUT_FLOOR_BPS = 1.0


class CommsParticleFilter:
    """Per-link belief tracker + connected-count aggregate."""

    name: str = "comms"

    def __init__(self, particles: int = 64) -> None:
        self._t = 0.0
        self._particles = particles
        self._links: dict[str, LinkEstimate] = {}

    def predict(self, dt: float) -> None:
        if dt > 0.0:
            self._t += dt

    def update(self, obs: Observation) -> None:
        for entry in obs.payload.get("links") or []:
            if not isinstance(entry, dict):
                continue
            link_id = entry.get("link_id")
            if not isinstance(link_id, str):
                continue
            try:
                rssi = float(entry.get("rssi_dbm", -120.0))
                loss = float(entry.get("loss_pct", 100.0))
                throughput = float(entry.get("throughput_bps", 0.0))
            except (TypeError, ValueError):
                continue
            connected = bool(entry.get("connected", False))
            self._links[link_id] = LinkEstimate(
                link_id=link_id,
                connected=connected and throughput >= _LIVE_THROUGHPUT_FLOOR_BPS,
                rssi_dbm=rssi,
                loss_pct=max(0.0, min(100.0, loss)),
                throughput_bps=max(0.0, throughput),
            )
        try:
            ts = float(obs.ts_s)
        except (TypeError, ValueError):
            return
        if math.isfinite(ts) and ts >= 0.0:
            self._t = ts

    def links(self) -> list[LinkEstimate]:
        return list(self._links.values())

    def state(self) -> Estimate:
        connected = sum(1 for link in self._links.values() if link.connected)
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={
                "connected_links": float(connected),
                "total_links": float(len(self._links)),
            },
            covariance={"connected_links": 0.25, "total_links": 0.0},
        )
