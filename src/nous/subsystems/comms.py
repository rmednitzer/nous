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
profile's ``max_age_s`` the link drops to ``connected=False`` and stamps
the transition (a cumulative ``age_out_count`` and ``last_aged_out_at_s``,
surfaced through ``comms_status``) until another transmission is recorded
or the controller intervenes through :meth:`set_link_state`.

The aggregator :func:`nous.state.comms_state.derive` consumes a list of
:class:`~nous.types.LinkEstimate` instances; :meth:`link_estimates`
produces that list directly so the engine and the estimator share one
schema.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..state.comms_state import CommsState, derive
from ..state.emcon import Emcon
from ..types import LinkEstimate, Observation
from .propagation import LinkPropagation, rician_fade_db, solve_link_budget

__all__ = ["CommsSubsystem", "Link"]

PositionFn = Callable[[], tuple[float, float, float]]

_LOG = logging.getLogger("nous.comms")


@dataclass
class Link:
    """One radio link with its nominal envelope and live state.

    ``capacity_bps`` is the link's currently sustainable rate. For a static link
    it is the rated ``bandwidth_bps``; for a link with a ``propagation`` block it
    is the SNR-derived capacity recomputed each tick (BL-048, ADR 0053). The
    ``range_m`` / ``path_loss_db`` / ``snr_db`` diagnostics are populated only
    for propagation links and surface through ``comms_status``.
    """

    link_id: str
    bandwidth_bps: float
    rssi_dbm_nominal: float
    loss_pct_nominal: float
    max_age_s: float
    rssi_dbm: float
    loss_pct: float
    throughput_bps: float
    capacity_bps: float = 0.0
    age_s: float = 0.0
    connected: bool = True
    forced_state: bool | None = None
    age_out_count: int = 0
    last_aged_out_at_s: float | None = None
    propagation: LinkPropagation | None = None
    range_m: float | None = None
    path_loss_db: float | None = None
    snr_db: float | None = None

    def as_estimate(self) -> LinkEstimate:
        live = self.is_live()
        return LinkEstimate(
            link_id=self.link_id,
            connected=live,
            rssi_dbm=self.rssi_dbm,
            loss_pct=self.loss_pct,
            throughput_bps=self.throughput_bps if live else 0.0,
            bandwidth_bps=self.bandwidth_bps,
            capacity_bps=self.capacity_bps if live else 0.0,
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
        position_fn: PositionFn | None = None,
    ) -> None:
        self.profile = profile
        self._rng = rng  # ADR 0019 follow-up: engine RNG seam
        # BL-048 / ADR 0053: a lazy device-position getter for the link budget.
        # Resolved at step() time, so it tolerates being constructed before the
        # position subsystem it reads.
        self._position_fn = position_fn
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
        self.emcon = Emcon(comms_cfg)

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
        """Record a transmission, returning the bytes accepted.

        A send is rejected (returns 0, and ``age_s`` is left unchanged) when the
        link is unknown, the controller has forced it down, the active EMCON
        profile forbids emitting on it (BL-060 / ADR 0065), its modeled
        ``capacity_bps`` has collapsed to zero (a propagation link below its SNR
        floor carries nothing; audit 2026-06-14b H-1), or ``n_bytes`` is
        non-positive. Only an accepted send resets ``age_s`` to 0 and updates
        ``throughput_bps`` to the achieved rate: the bits sent over the interval
        since this link last transmitted, capped at the link's sustainable
        ``capacity_bps`` (the rated bandwidth for a static link, the SNR-derived
        capacity for a propagation link; achieved-rate audit COMMS-3 / ADR 0051,
        the capacity cap per BL-048 / ADR 0053).
        """
        link = self._links.get(link_id)
        if link is None:
            return 0
        if link.forced_state is False:
            return 0
        if not self.emcon.permits(link_id):
            return 0
        if link.capacity_bps <= 0.0:
            # A propagation link driven below its SNR floor carries nothing:
            # reject the send and stamp the zero achieved rate rather than
            # reporting bytes accepted on a dead link (audit 2026-06-14b H-1,
            # consistent with the forced-down guard above).
            link.throughput_bps = 0.0
            return 0
        amount = max(0, int(n_bytes))
        if amount <= 0:
            return 0
        bits = float(amount) * 8.0
        elapsed = link.age_s
        # An achieved rate (bits per second), not the raw packet size. No
        # elapsed time (the first send, or two sends in one instant) reports
        # the link capacity instead of dividing by zero; the cap holds the rate
        # to the SNR-derived sustainable capacity, which equals the rated
        # bandwidth for a static link and falls on a poor channel (ADR 0051
        # rate, capped by the ADR 0053 capacity).
        ceiling = link.capacity_bps
        rate = ceiling if elapsed <= 0.0 else bits / elapsed
        link.throughput_bps = min(rate, ceiling)
        link.age_s = 0.0
        link.connected = True
        return amount

    def step(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        device_pos = self._device_position()
        for link in self._links.values():
            if (
                link.propagation is not None
                and device_pos is not None
                and link.forced_state is None
            ):
                # BL-048 / ADR 0053: re-solve the link budget from the geometry.
                # A forced link keeps its override (the controller / scenario
                # escape hatch wins over the physics), so the recompute is gated
                # on forced_state being clear.
                self._apply_propagation(link, device_pos)
            was_live = link.is_live()
            link.age_s += dt
            if link.age_s > link.max_age_s and link.forced_state is None:
                link.connected = False
                link.throughput_bps = 0.0
            if was_live and not link.is_live():
                # genuine live -> aged-out transition (COMMS-2): stamp it so a
                # controller polling comms_status sees the drop, and the
                # cumulative count survives a flap a coarse poll would miss.
                # Gating on is_live() rather than the raw connected flag means a
                # link that went stale while forced down is not miscounted when
                # the override is later cleared.
                link.age_out_count += 1
                link.last_aged_out_at_s = self._t
                _LOG.info(
                    "comms link %s aged out at t=%.3fs (age_s %.3f > max %.3f)",
                    link.link_id,
                    self._t,
                    link.age_s,
                    link.max_age_s,
                )

    def _device_position(self) -> tuple[float, float, float] | None:
        if self._position_fn is None:
            return None
        lat, lon, alt = self._position_fn()
        return float(lat), float(lon), float(alt)

    def _apply_propagation(
        self, link: Link, device_pos: tuple[float, float, float]
    ) -> None:
        prop = link.propagation
        if prop is None:
            return
        shadow = 0.0
        fade = 0.0
        if self._rng is not None:
            if prop.shadowing_sigma_db > 0.0:
                shadow = float(self._rng.normal(0.0, prop.shadowing_sigma_db))
            if prop.rician_k_db is not None:
                # BL-088 / ADR 0054: a multipath fast-fade draw on top of the
                # log-normal shadowing, both from the engine RNG seam.
                fade = rician_fade_db(self._rng, prop.rician_k_db)
        budget = solve_link_budget(
            prop,
            device_lat=device_pos[0],
            device_lon=device_pos[1],
            device_alt_m=device_pos[2],
            bandwidth_bps=link.bandwidth_bps,
            shadowing_db=shadow,
            fast_fade_db=fade,
        )
        link.rssi_dbm = budget.rssi_dbm
        link.loss_pct = budget.loss_pct
        link.capacity_bps = budget.capacity_bps
        link.range_m = budget.range_m
        link.path_loss_db = budget.path_loss_db
        link.snr_db = budget.snr_db

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
                "capacity_bps": link.capacity_bps if link.is_live() else 0.0,
                # Rated bandwidth is static (not gated on liveness); it lets the
                # filter's LinkEstimate carry a bandwidth so comms_state uses the
                # per-link capacity fraction, not the legacy floor (M-1).
                "bandwidth_bps": link.bandwidth_bps,
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
        # A static link's sustainable capacity is its rated bandwidth, so the
        # ADR 0053 SNR coupling is inert without a propagation block. A
        # propagation link overwrites this each tick from the link budget.
        capacity_bps=bandwidth_bps,
        propagation=LinkPropagation.from_profile(entry),
    )


def _link_truth(link: Link) -> Mapping[str, Any]:
    live = link.is_live()
    return {
        "link_id": link.link_id,
        "bandwidth_bps": link.bandwidth_bps,
        "rssi_dbm_nominal": link.rssi_dbm_nominal,
        "loss_pct_nominal": link.loss_pct_nominal,
        "max_age_s": link.max_age_s,
        "rssi_dbm": link.rssi_dbm,
        "loss_pct": link.loss_pct,
        "throughput_bps": link.throughput_bps if live else 0.0,
        "capacity_bps": link.capacity_bps if live else 0.0,
        "age_s": link.age_s,
        "connected": live,
        "forced": link.forced_state is not None,
        "age_out_count": link.age_out_count,
        "last_aged_out_at_s": link.last_aged_out_at_s,
        "propagation": link.propagation is not None,
        "range_m": link.range_m,
        "path_loss_db": link.path_loss_db,
        "snr_db": link.snr_db,
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
