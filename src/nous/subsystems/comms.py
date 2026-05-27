"""Comms subsystem: per-link envelopes, age-out, and FSM state derivation (BL-012).

The simulator's controller cares about three things from comms:

* Which links are present at all (a profile-derived inventory --
  ``profile["comms"]["links"]`` lists ``id``, ``bandwidth_bps``,
  ``rssi_dbm_nominal``, ``loss_pct_nominal``, ``max_age_s``).
* Which links are *live* right now (signal seen within
  ``max_age_s`` of the last transmission).
* The aggregate :class:`~nous.state.comms_state.CommsState` label
  the FSM uses to gate the inference-fallback ladder and any
  cloud-bound tools.

The subsystem is the ground truth: live RSSI, loss percentage, and
throughput per link, plus an ``age_s`` counter that increments each
tick and resets on a successful :meth:`tx`. When ``age_s`` exceeds the
profile's ``max_age_s`` the link silently drops to ``connected=False``
until another transmission is recorded or the controller intervenes
through :meth:`set_link_state`.

The aggregator :func:`nous.state.comms_state.derive` consumes a list of
:class:`~nous.types.LinkEstimate` instances; :meth:`link_estimates`
produces that list directly so the engine and the estimator share one
schema.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..state.comms_state import CommsState, derive
from ..types import LinkEstimate, Observation

__all__ = ["CommsSubsystem", "Link"]


@dataclass
class Link:
    """One radio link with its nominal envelope and live state."""

    link_id: str
    bandwidth_bps: float
    rssi_dbm_nominal: float
    loss_pct_nominal: float
    max_age_s: float
    rssi_dbm: float
    loss_pct: float
    throughput_bps: float
    age_s: float = 0.0
    connected: bool = True
    forced_state: bool | None = None

    def as_estimate(self) -> LinkEstimate:
        return LinkEstimate(
            link_id=self.link_id,
            connected=self.is_live(),
            rssi_dbm=self.rssi_dbm,
            loss_pct=self.loss_pct,
            throughput_bps=self.throughput_bps if self.is_live() else 0.0,
        )

    def is_live(self) -> bool:
        if self.forced_state is not None:
            return self.forced_state
        return self.connected and self.age_s <= self.max_age_s


class CommsSubsystem:
    """Radios + first-order link-budget model.

    Holds one :class:`Link` per entry in ``profile["comms"]["links"]``.
    The subsystem owns the live-state mutation; the estimator
    consumes :meth:`link_estimates` to produce a coherent set of
    beliefs for the controller.
    """

    name: str = "comms"

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.profile = profile
        self._rng = rng  # ADR 0019 follow-up: engine RNG seam
        comms_cfg = profile.get("comms") or {}
        raw_links = comms_cfg.get("links") or []
        self._links: dict[str, Link] = {}
        for entry in raw_links:
            if not isinstance(entry, Mapping):
                continue
            link = _link_from_profile(entry)
            if link is None:
                continue
            self._links[link.link_id] = link
        self._t = 0.0

    @property
    def link_ids(self) -> list[str]:
        return list(self._links.keys())

    def __iter__(self) -> Iterator[Link]:
        return iter(self._links.values())

    def link(self, link_id: str) -> Link | None:
        return self._links.get(link_id)

    def set_link_state(
        self,
        link_id: str,
        *,
        rssi_dbm: float | None = None,
        loss_pct: float | None = None,
        throughput_bps: float | None = None,
        connected: bool | None = None,
    ) -> None:
        """Scenario / controller seam: override a link's live state.

        ``connected`` is sticky -- once set it overrides the age-out
        rule until cleared with :meth:`clear_link_override`.
        """
        link = self._links.get(link_id)
        if link is None:
            return
        if rssi_dbm is not None:
            link.rssi_dbm = float(rssi_dbm)
        if loss_pct is not None:
            link.loss_pct = max(0.0, min(100.0, float(loss_pct)))
        if throughput_bps is not None:
            link.throughput_bps = max(0.0, float(throughput_bps))
        if connected is not None:
            link.forced_state = bool(connected)

    def clear_link_override(self, link_id: str) -> None:
        """Release a sticky ``connected`` override set by :meth:`set_link_state`."""
        link = self._links.get(link_id)
        if link is None:
            return
        link.forced_state = None

    def tx(self, link_id: str, n_bytes: int) -> int:
        """Record a transmission. Resets ``age_s`` and returns bytes accepted.

        A transmission on a link that the controller has forced down
        is rejected (returns 0). Otherwise ``age_s`` is reset to 0 and
        a coarse throughput figure is updated.
        """
        link = self._links.get(link_id)
        if link is None:
            return 0
        if link.forced_state is False:
            return 0
        amount = max(0, int(n_bytes))
        if amount <= 0:
            return 0
        link.age_s = 0.0
        link.connected = True
        link.throughput_bps = float(amount) * 8.0
        return amount

    def step(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        for link in self._links.values():
            link.age_s += dt
            if link.age_s > link.max_age_s and link.forced_state is None:
                link.connected = False
                link.throughput_bps = 0.0

    def link_estimates(self) -> list[LinkEstimate]:
        return [link.as_estimate() for link in self._links.values()]

    def derive_state(self) -> tuple[CommsState, str]:
        return derive(self.link_estimates())

    def truth(self) -> Mapping[str, Any]:
        return {
            "links": [_link_truth(link) for link in self._links.values()],
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        payload_links = [
            {
                "link_id": link.link_id,
                "rssi_dbm": link.rssi_dbm,
                "loss_pct": link.loss_pct,
                "throughput_bps": link.throughput_bps if link.is_live() else 0.0,
                "connected": link.is_live(),
            }
            for link in self._links.values()
        ]
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"links": payload_links},
            noise={"rssi_dbm_sigma": 2.0, "loss_pct_sigma": 0.5},
        )


def _link_from_profile(entry: Mapping[str, Any]) -> Link | None:
    link_id = entry.get("id")
    if not isinstance(link_id, str) or not link_id:
        return None
    try:
        bandwidth_bps = float(entry.get("bandwidth_bps", 0.0))
        rssi_nominal = float(entry.get("rssi_dbm_nominal", -100.0))
        loss_nominal = float(entry.get("loss_pct_nominal", 0.0))
        max_age = float(entry.get("max_age_s", 30.0))
    except (TypeError, ValueError):
        return None
    nominal_throughput = bandwidth_bps * (1.0 - max(0.0, min(100.0, loss_nominal)) / 100.0)
    return Link(
        link_id=link_id,
        bandwidth_bps=bandwidth_bps,
        rssi_dbm_nominal=rssi_nominal,
        loss_pct_nominal=loss_nominal,
        max_age_s=max(0.0, max_age),
        rssi_dbm=rssi_nominal,
        loss_pct=max(0.0, min(100.0, loss_nominal)),
        throughput_bps=nominal_throughput,
    )


def _link_truth(link: Link) -> Mapping[str, Any]:
    return {
        "link_id": link.link_id,
        "bandwidth_bps": link.bandwidth_bps,
        "rssi_dbm_nominal": link.rssi_dbm_nominal,
        "loss_pct_nominal": link.loss_pct_nominal,
        "max_age_s": link.max_age_s,
        "rssi_dbm": link.rssi_dbm,
        "loss_pct": link.loss_pct,
        "throughput_bps": link.throughput_bps if link.is_live() else 0.0,
        "age_s": link.age_s,
        "connected": link.is_live(),
        "forced": link.forced_state is not None,
    }


def link_ids_from_profile(profile: Mapping[str, Any]) -> Sequence[str]:
    """Helper for tests / scenarios: list link ids declared by a profile."""
    cfg = profile.get("comms") or {}
    out: list[str] = []
    for entry in cfg.get("links") or []:
        if isinstance(entry, Mapping):
            link_id = entry.get("id")
            if isinstance(link_id, str):
                out.append(link_id)
    return out
