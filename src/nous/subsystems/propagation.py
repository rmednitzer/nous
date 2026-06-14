"""First-order RF link budget for the propagation-aware comms model (BL-048).

The comms subsystem (``subsystems/comms.py``) holds each link's live RSSI, loss,
and capacity. Without this module those sit at the profile's static nominal
forever. With a ``propagation`` block on a link, this module turns the geometry
between the device and the link's peer into a received signal level, and that
level into the link's RSSI, packet loss, and SNR-derived capacity, each tick.

The model is deliberately first-order (ADR 0053): a Friis free-space path loss, a
constant excess-loss margin standing in for terrain and obstruction, and a
log-normal shadowing draw for fast variation. The caller draws the shadowing
sample from the engine RNG (ADR 0019) and passes it in, so every function here is
pure and deterministic given its inputs. Higher-fidelity propagation (terrain
raytracing, multipath, mesh routing) is the BL-088 horizon.

Two monotonicity properties hold by construction and are what make the model
legible: as the device moves away from the peer the range grows, the path loss
grows, the RSSI falls, the packet loss rises, and the SNR-derived capacity
shrinks. ``test_propagation`` and the strengthened ``test_subsystem_invariants``
pin them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "LinkBudget",
    "LinkPropagation",
    "capacity_bps",
    "free_space_path_loss_db",
    "received_power_dbm",
    "rssi_to_loss_pct",
    "slant_range_m",
    "solve_link_budget",
]

_SPEED_OF_LIGHT_M_S = 299_792_458.0
_EARTH_RADIUS_M = 6_371_000.0
_MIN_RANGE_M = 1.0
# 20 * log10(4 * pi / c): the frequency / distance independent term of Friis.
_FRIIS_CONSTANT_DB = 20.0 * math.log10(4.0 * math.pi / _SPEED_OF_LIGHT_M_S)


@dataclass(frozen=True)
class LinkPropagation:
    """Per-link RF link-budget parameters parsed from a profile ``propagation`` block.

    Every field has a default, so a profile declares only what it cares about. A
    link with no ``peer`` has no geometry to solve and is left static; that is
    why :meth:`from_profile` returns ``None`` in that case.
    """

    peer_lat: float
    peer_lon: float
    peer_alt_m: float
    tx_power_dbm: float = 30.0
    frequency_hz: float = 2.4e9
    tx_gain_dbi: float = 2.0
    rx_gain_dbi: float = 2.0
    excess_loss_db: float = 0.0
    shadowing_sigma_db: float = 0.0
    noise_floor_dbm: float = -100.0
    snr_floor_db: float = 3.0
    snr_full_db: float = 25.0
    good_rssi_dbm: float = -70.0
    sensitivity_dbm: float = -100.0
    loss_floor_pct: float = 0.0

    @classmethod
    def from_profile(cls, entry: Mapping[str, Any]) -> LinkPropagation | None:
        """Build a :class:`LinkPropagation` from a link's profile entry.

        Reads the optional ``propagation`` sub-block and its nested ``peer``
        position. Returns ``None`` when the block or the peer is absent or
        malformed, so the link falls back to static-nominal behaviour.
        """
        block = entry.get("propagation")
        if not isinstance(block, Mapping):
            return None
        peer = block.get("peer")
        if not isinstance(peer, Mapping):
            return None
        try:
            peer_lat = float(peer["lat"])
            peer_lon = float(peer["lon"])
            peer_alt_m = float(peer.get("alt_m", 0.0))
        except (KeyError, TypeError, ValueError):
            return None

        def _f(key: str, default: float) -> float:
            try:
                return float(block.get(key, default))
            except (TypeError, ValueError):
                return default

        return cls(
            peer_lat=peer_lat,
            peer_lon=peer_lon,
            peer_alt_m=peer_alt_m,
            tx_power_dbm=_f("tx_power_dbm", 30.0),
            frequency_hz=max(1.0, _f("frequency_hz", 2.4e9)),
            tx_gain_dbi=_f("tx_gain_dbi", 2.0),
            rx_gain_dbi=_f("rx_gain_dbi", 2.0),
            excess_loss_db=_f("excess_loss_db", 0.0),
            shadowing_sigma_db=max(0.0, _f("shadowing_sigma_db", 0.0)),
            noise_floor_dbm=_f("noise_floor_dbm", -100.0),
            snr_floor_db=_f("snr_floor_db", 3.0),
            snr_full_db=_f("snr_full_db", 25.0),
            good_rssi_dbm=_f("good_rssi_dbm", -70.0),
            sensitivity_dbm=_f("sensitivity_dbm", -100.0),
            loss_floor_pct=_clip(_f("loss_floor_pct", 0.0), 0.0, 100.0),
        )


@dataclass(frozen=True)
class LinkBudget:
    """The solved RF state of one link: what the geometry produces this tick."""

    range_m: float
    path_loss_db: float
    rssi_dbm: float
    snr_db: float
    capacity_bps: float
    loss_pct: float


def slant_range_m(
    lat1: float,
    lon1: float,
    alt1_m: float,
    lat2: float,
    lon2: float,
    alt2_m: float,
) -> float:
    """Great-circle ground distance combined with the altitude delta, in metres.

    The ground distance is a haversine on a spherical Earth; the altitude delta
    is added in quadrature to give the line-of-sight slant range. Good to a
    fraction of a percent over the tens-of-kilometres ranges the twin models.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    ground = 2.0 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))
    return math.hypot(ground, alt2_m - alt1_m)


def free_space_path_loss_db(range_m: float, frequency_hz: float) -> float:
    """Friis free-space path loss in dB.

    Clamped at a one-metre minimum range so a coincident peer does not produce a
    negative or infinite loss.
    """
    d = max(_MIN_RANGE_M, range_m)
    f = max(1.0, frequency_hz)
    return 20.0 * math.log10(d) + 20.0 * math.log10(f) + _FRIIS_CONSTANT_DB


def received_power_dbm(
    tx_power_dbm: float,
    tx_gain_dbi: float,
    rx_gain_dbi: float,
    path_loss_db: float,
    excess_loss_db: float,
    shadowing_db: float,
) -> float:
    """Link-budget sum: transmit power and antenna gains minus the losses."""
    return (
        tx_power_dbm
        + tx_gain_dbi
        + rx_gain_dbi
        - path_loss_db
        - excess_loss_db
        - shadowing_db
    )


def capacity_bps(
    bandwidth_bps: float,
    snr_db: float,
    snr_floor_db: float,
    snr_full_db: float,
) -> float:
    """Bandwidth derated by an adaptive-modulation fraction of the SNR.

    The fraction ramps linearly from zero at ``snr_floor_db`` (link unusable) to
    one at ``snr_full_db`` (link at its rated rate). Non-decreasing in SNR, which
    is the ADR 0020 invariant.
    """
    bw = max(0.0, bandwidth_bps)
    if snr_full_db <= snr_floor_db:
        return bw if snr_db >= snr_full_db else 0.0
    frac = _clip((snr_db - snr_floor_db) / (snr_full_db - snr_floor_db), 0.0, 1.0)
    return bw * frac


def rssi_to_loss_pct(
    rssi_dbm: float,
    good_rssi_dbm: float,
    sensitivity_dbm: float,
    loss_floor_pct: float,
) -> float:
    """Packet loss from RSSI: the loss floor at a strong signal, 100% at sensitivity.

    Linear between ``good_rssi_dbm`` and ``sensitivity_dbm``. Non-increasing in
    RSSI (so non-decreasing as the device moves away), the companion of the SNR
    capacity ramp.
    """
    floor = _clip(loss_floor_pct, 0.0, 100.0)
    if good_rssi_dbm <= sensitivity_dbm:
        return floor if rssi_dbm >= good_rssi_dbm else 100.0
    frac = _clip(
        (good_rssi_dbm - rssi_dbm) / (good_rssi_dbm - sensitivity_dbm), 0.0, 1.0
    )
    return floor + frac * (100.0 - floor)


def solve_link_budget(
    prop: LinkPropagation,
    *,
    device_lat: float,
    device_lon: float,
    device_alt_m: float,
    bandwidth_bps: float,
    shadowing_db: float = 0.0,
) -> LinkBudget:
    """Solve the full link budget for one link given the device position.

    ``shadowing_db`` is supplied by the caller (drawn from the engine RNG) so
    this function stays pure and deterministic; pass ``0.0`` for the noise-free
    geometry. Returns the range, path loss, RSSI, SNR, SNR-derived capacity, and
    packet loss that the comms subsystem writes onto the link.
    """
    rng_m = slant_range_m(
        device_lat,
        device_lon,
        device_alt_m,
        prop.peer_lat,
        prop.peer_lon,
        prop.peer_alt_m,
    )
    path_loss = free_space_path_loss_db(rng_m, prop.frequency_hz)
    rssi = received_power_dbm(
        prop.tx_power_dbm,
        prop.tx_gain_dbi,
        prop.rx_gain_dbi,
        path_loss,
        prop.excess_loss_db,
        shadowing_db,
    )
    snr = rssi - prop.noise_floor_dbm
    cap = capacity_bps(bandwidth_bps, snr, prop.snr_floor_db, prop.snr_full_db)
    loss = rssi_to_loss_pct(
        rssi, prop.good_rssi_dbm, prop.sensitivity_dbm, prop.loss_floor_pct
    )
    return LinkBudget(
        range_m=rng_m,
        path_loss_db=path_loss,
        rssi_dbm=rssi,
        snr_db=snr,
        capacity_bps=cap,
        loss_pct=loss,
    )


def _clip(value: float, low: float, high: float) -> float:
    if not math.isfinite(value):
        return low
    if value < low:
        return low
    if value > high:
        return high
    return value
