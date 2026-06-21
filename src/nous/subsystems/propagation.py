"""First-order RF link budget for the propagation-aware comms model (BL-048).

The comms subsystem (``subsystems/comms.py``) holds each link's live RSSI, loss,
and capacity. Without this module those sit at the profile's static nominal
forever. With a ``propagation`` block on a link, this module turns the geometry
between the device and the link's peer into a received signal level, and that
level into the link's RSSI, packet loss, and SNR-derived capacity, each tick.

The base model is first-order (ADR 0053): a Friis free-space path loss, a
constant excess-loss margin standing in for terrain and obstruction, and a
log-normal shadowing draw for fast variation. BL-088 / ADR 0054 raises the
fidelity with five additive, opt-in upgrades: a log-distance path-loss exponent
(the environment, not just free space), a single knife-edge diffraction loss (a
discrete terrain obstruction), a kTB thermal-noise floor, a directional antenna
pattern keyed on the bearing to the peer, and a Rician multipath fast-fade draw.
Every upgrade defaults to reproduce the ADR 0053 budget exactly. The caller draws
the two stochastic terms (shadowing and fast fade) from the engine RNG (ADR 0019)
and passes them in, so every function here is pure and deterministic given its
inputs.

Two monotonicity properties hold by construction and are what make the model
legible: as the device moves away from the peer the range grows, the path loss
grows, the RSSI falls, the packet loss rises, and the SNR-derived capacity
shrinks. ``test_propagation`` and the strengthened ``test_subsystem_invariants``
pin them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "LinkBudget",
    "LinkPropagation",
    "antenna_gain_offset_db",
    "bearing_deg",
    "bullington_diffraction_db",
    "capacity_bps",
    "free_space_path_loss_db",
    "knife_edge_diffraction_db",
    "log_distance_path_loss_db",
    "received_power_dbm",
    "rician_fade_db",
    "rssi_to_loss_pct",
    "slant_range_m",
    "solve_link_budget",
    "thermal_noise_floor_dbm",
]

_SPEED_OF_LIGHT_M_S = 299_792_458.0
_EARTH_RADIUS_M = 6_371_000.0
_MIN_RANGE_M = 1.0
# 20 * log10(4 * pi / c): the frequency / distance independent term of Friis.
_FRIIS_CONSTANT_DB = 20.0 * math.log10(4.0 * math.pi / _SPEED_OF_LIGHT_M_S)
# Johnson-Nyquist thermal noise power spectral density at 290 K: kTB in dBm/Hz.
_THERMAL_NOISE_DBM_PER_HZ = -173.975


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
    # BL-088 / ADR 0054 higher-fidelity fields. Each default reproduces the
    # ADR 0053 free-space, isotropic, constant-noise-floor, fade-free budget.
    path_loss_exponent: float = 2.0
    obstruction_distance_m: float | None = None
    obstruction_height_m: float = 0.0
    channel_bandwidth_hz: float | None = None
    noise_figure_db: float = 0.0
    antenna_boresight_deg: float | None = None
    antenna_half_beamwidth_deg: float = 60.0
    antenna_front_to_back_db: float = 20.0
    rician_k_db: float | None = None
    # BL-089: opt in to multi-edge diffraction over a sampled terrain path. When
    # false (the default) the single-knife-edge model above is unchanged.
    use_terrain: bool = False
    terrain_samples: int = 16

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

        def _opt(key: str) -> float | None:
            raw = block.get(key)
            if raw is None:
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        def _pos_opt(key: str) -> float | None:
            """An optional float that must be positive; non-positive reads as unset.

            A non-physical (zero or negative) channel bandwidth would otherwise
            drive the kTB floor to its 1 Hz value, an unrealistically optimistic
            noise floor; treating it as unset falls back to the configured
            constant floor instead (fail conservative).
            """
            value = _opt(key)
            return value if value is not None and value > 0.0 else None

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
            path_loss_exponent=max(0.0, _f("path_loss_exponent", 2.0)),
            obstruction_distance_m=_opt("obstruction_distance_m"),
            obstruction_height_m=_f("obstruction_height_m", 0.0),
            channel_bandwidth_hz=_pos_opt("channel_bandwidth_hz"),
            noise_figure_db=max(0.0, _f("noise_figure_db", 0.0)),
            antenna_boresight_deg=_opt("antenna_boresight_deg"),
            antenna_half_beamwidth_deg=max(
                1.0, _f("antenna_half_beamwidth_deg", 60.0)
            ),
            antenna_front_to_back_db=max(0.0, _f("antenna_front_to_back_db", 20.0)),
            rician_k_db=_opt("rician_k_db"),
            use_terrain=bool(block.get("use_terrain", False)),
            terrain_samples=max(2, int(_f("terrain_samples", 16.0))),
        )


@dataclass(frozen=True)
class LinkBudget:
    """The solved RF state of one link: what the geometry produces this tick.

    ``path_loss_db`` is the total propagation loss (the log-distance path loss
    plus any knife-edge diffraction); ``diffraction_loss_db`` and
    ``antenna_offset_db`` break out the BL-088 contributions, and
    ``noise_floor_dbm`` is the floor the SNR was taken against.
    """

    range_m: float
    path_loss_db: float
    rssi_dbm: float
    snr_db: float
    capacity_bps: float
    loss_pct: float
    diffraction_loss_db: float = 0.0
    antenna_offset_db: float = 0.0
    noise_floor_dbm: float = -100.0


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


def log_distance_path_loss_db(
    range_m: float, frequency_hz: float, exponent: float = 2.0
) -> float:
    """Log-distance path loss: free space at ``exponent == 2``, steeper above.

    ``PL = FSPL(1 m, f) + 10 * n * log10(d)``. An ``exponent`` of 2 reproduces
    :func:`free_space_path_loss_db` exactly; 2.7 to 3.5 models urban clutter, and
    4 or above a heavily obstructed or forested path (BL-088, ADR 0054).
    """
    d = max(_MIN_RANGE_M, range_m)
    n = max(0.0, exponent)
    return free_space_path_loss_db(_MIN_RANGE_M, frequency_hz) + 10.0 * n * math.log10(d)


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, degrees CW from north."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        dlambda
    )
    return math.degrees(math.atan2(y, x)) % 360.0


def knife_edge_diffraction_db(
    obstruction_height_m: float,
    los_height_m: float,
    d1_m: float,
    d2_m: float,
    frequency_hz: float,
) -> float:
    """Single knife-edge diffraction loss (ITU-R P.526 approximation), in dB.

    ``los_height_m`` is the line-of-sight height at the obstruction's location;
    the obstruction's height above it drives the Fresnel parameter ``v``. Returns
    0 for an obstruction at or below the line of sight (``v <= -0.78``). ``d1`` and
    ``d2`` are the along-path distances from each endpoint to the obstruction.
    """
    if d1_m <= 0.0 or d2_m <= 0.0:
        return 0.0
    h = obstruction_height_m - los_height_m
    wavelength = _SPEED_OF_LIGHT_M_S / max(1.0, frequency_hz)
    v = h * math.sqrt(2.0 / wavelength * (1.0 / d1_m + 1.0 / d2_m))
    return _fresnel_diffraction_loss_db(v)


def _fresnel_diffraction_loss_db(v: float) -> float:
    """ITU-R P.526 single knife-edge loss ``J(v)`` in dB; 0 for ``v <= -0.78``.

    The shared diffraction kernel: the single knife edge computes one ``v`` from
    its geometry, the Bullington method computes one ``v`` for its equivalent edge,
    and both pass it here. ``v <= -0.78`` is a clear path (obstacle below the
    first Fresnel zone), so the loss is zero.
    """
    if v <= -0.78:
        return 0.0
    return 6.9 + 20.0 * math.log10(math.sqrt((v - 0.1) ** 2 + 1.0) + v - 0.1)


def bullington_diffraction_db(
    profile: Sequence[tuple[float, float]],
    tx_height_m: float,
    rx_height_m: float,
    frequency_hz: float,
) -> float:
    """Multi-edge diffraction loss over a terrain path profile (Bullington), in dB.

    ``profile`` is the sampled path ``[(distance_from_tx_m, terrain_elevation_m), ...]``
    including both endpoints (BL-089); ``tx_height_m`` and ``rx_height_m`` are the
    device and peer antenna heights on the same datum as the terrain elevations.
    The Bullington construction (ITU-R P.526) takes the steepest obstacle seen from
    each end, intersects their rays to form one equivalent knife edge, and applies
    :func:`_fresnel_diffraction_loss_db` once. With a single interior obstacle it
    reduces exactly to :func:`knife_edge_diffraction_db`: the Bullington point lands
    on that obstacle and ``2 d / (d1 d2) == 2 (1/d1 + 1/d2)`` when ``d1 + d2 = d``.
    Returns 0 for a path whose terrain stays at or below the line of sight.
    """
    if len(profile) < 2:
        return 0.0
    total_d = profile[-1][0]
    if total_d <= 0.0:
        return 0.0
    interior = [(di, hi) for di, hi in profile if 0.0 < di < total_d]
    if not interior:
        return 0.0
    los_slope = (rx_height_m - tx_height_m) / total_d
    s_tx = max((hi - tx_height_m) / di for di, hi in interior)
    if s_tx <= los_slope:
        return 0.0
    s_rx = max((hi - rx_height_m) / (total_d - di) for di, hi in interior)
    denom = s_tx + s_rx
    if denom <= 0.0:
        return 0.0
    d_b = (rx_height_m - tx_height_m + s_rx * total_d) / denom
    if d_b <= 0.0 or d_b >= total_d:
        return 0.0
    wavelength = _SPEED_OF_LIGHT_M_S / max(1.0, frequency_hz)
    excess_h = (s_tx - los_slope) * d_b
    v = excess_h * math.sqrt(2.0 * total_d / (wavelength * d_b * (total_d - d_b)))
    return _fresnel_diffraction_loss_db(v)


def antenna_gain_offset_db(
    bearing_to_peer_deg: float,
    boresight_deg: float,
    half_beamwidth_deg: float,
    front_to_back_db: float,
) -> float:
    """Directional antenna gain roll-off from the off-boresight angle, in dB (<= 0).

    A parabolic-in-dB main lobe: 0 at boresight, -3 dB at ``half_beamwidth_deg``
    off boresight, floored at ``-front_to_back_db`` for the back lobe. Never
    positive, so it only ever reduces the isotropic gain already in the budget.
    """
    theta = abs((bearing_to_peer_deg - boresight_deg + 180.0) % 360.0 - 180.0)
    hpbw = max(1.0, half_beamwidth_deg)
    rolloff = 3.0 * (theta / hpbw) ** 2
    return -min(rolloff, max(0.0, front_to_back_db))


def thermal_noise_floor_dbm(channel_bandwidth_hz: float, noise_figure_db: float) -> float:
    """Johnson-Nyquist noise floor, ``kTB + NF`` in dBm.

    ``-173.975 dBm/Hz`` (kT at 290 K) plus ``10 log10(B)`` plus the receiver noise
    figure. Replaces the per-link constant floor when a channel bandwidth is
    configured (BL-088, ADR 0054).
    """
    b = max(1.0, channel_bandwidth_hz)
    return _THERMAL_NOISE_DBM_PER_HZ + 10.0 * math.log10(b) + noise_figure_db


def rician_fade_db(rng: np.random.Generator, k_db: float) -> float:
    """A Rician multipath fast-fade loss sample in dB (positive attenuates).

    ``k_db`` is the Rician K-factor (specular-to-scattered power ratio) in dB: a
    large K is near line of sight with little fading, ``K = 0`` is Rayleigh. The
    underlying power gain has unit mean; the returned value is the negative of its
    dB, so it is a loss term consistent with the shadowing draw (mostly positive,
    occasionally negative on a constructive peak). Drawn from the engine RNG.
    """
    k = 10.0 ** (k_db / 10.0)
    s = math.sqrt(k / (k + 1.0))
    sigma = math.sqrt(1.0 / (2.0 * (k + 1.0)))
    i = s + sigma * float(rng.normal())
    q = sigma * float(rng.normal())
    power = i * i + q * q
    return -10.0 * math.log10(max(power, 1e-12))


def solve_link_budget(
    prop: LinkPropagation,
    *,
    device_lat: float,
    device_lon: float,
    device_alt_m: float,
    bandwidth_bps: float,
    shadowing_db: float = 0.0,
    fast_fade_db: float = 0.0,
    terrain_profile: Sequence[tuple[float, float]] | None = None,
) -> LinkBudget:
    """Solve the full link budget for one link given the device position.

    ``shadowing_db`` and ``fast_fade_db`` are the two stochastic loss terms,
    supplied by the caller (drawn from the engine RNG) so this function stays pure
    and deterministic; pass ``0.0`` for the noise-free geometry. The four
    deterministic BL-088 upgrades (log-distance exponent, knife-edge diffraction,
    directional antenna, kTB noise floor) are read from ``prop``. When the link
    opts into terrain (``prop.use_terrain``) and a sampled ``terrain_profile`` is
    supplied, multi-edge Bullington diffraction over that path replaces the single
    configured knife edge (BL-089). Returns the range, total path loss, RSSI, SNR,
    SNR-derived capacity, packet loss, and the diagnostic breakdown.
    """
    rng_m = slant_range_m(
        device_lat,
        device_lon,
        device_alt_m,
        prop.peer_lat,
        prop.peer_lon,
        prop.peer_alt_m,
    )
    path_loss = log_distance_path_loss_db(
        rng_m, prop.frequency_hz, prop.path_loss_exponent
    )

    diffraction = 0.0
    if prop.use_terrain and terrain_profile is not None:
        # BL-089: multi-edge diffraction over the sampled terrain path replaces the
        # single configured knife edge when the link opts into terrain.
        diffraction = bullington_diffraction_db(
            terrain_profile, device_alt_m, prop.peer_alt_m, prop.frequency_hz
        )
    else:
        obstruction = prop.obstruction_distance_m
        if obstruction is not None and 0.0 < obstruction < rng_m:
            los_height = device_alt_m + (prop.peer_alt_m - device_alt_m) * (
                obstruction / rng_m
            )
            diffraction = knife_edge_diffraction_db(
                prop.obstruction_height_m,
                los_height,
                obstruction,
                rng_m - obstruction,
                prop.frequency_hz,
            )

    antenna_offset = 0.0
    if prop.antenna_boresight_deg is not None:
        antenna_offset = antenna_gain_offset_db(
            bearing_deg(device_lat, device_lon, prop.peer_lat, prop.peer_lon),
            prop.antenna_boresight_deg,
            prop.antenna_half_beamwidth_deg,
            prop.antenna_front_to_back_db,
        )

    rssi = (
        received_power_dbm(
            prop.tx_power_dbm,
            prop.tx_gain_dbi,
            prop.rx_gain_dbi,
            path_loss + diffraction,
            prop.excess_loss_db,
            shadowing_db + fast_fade_db,
        )
        + antenna_offset
    )

    if prop.channel_bandwidth_hz is not None and prop.channel_bandwidth_hz > 0.0:
        # Fail conservative: a non-positive bandwidth or a negative noise figure
        # would lower the floor and flatter the SNR, so a directly-built
        # LinkPropagation with bad values still falls back to the constant floor
        # and a clamped noise figure (audit / PR #139 review).
        noise_floor = thermal_noise_floor_dbm(
            prop.channel_bandwidth_hz, max(0.0, prop.noise_figure_db)
        )
    else:
        noise_floor = prop.noise_floor_dbm

    snr = rssi - noise_floor
    cap = capacity_bps(bandwidth_bps, snr, prop.snr_floor_db, prop.snr_full_db)
    loss = rssi_to_loss_pct(
        rssi, prop.good_rssi_dbm, prop.sensitivity_dbm, prop.loss_floor_pct
    )
    return LinkBudget(
        range_m=rng_m,
        path_loss_db=path_loss + diffraction,
        rssi_dbm=rssi,
        snr_db=snr,
        capacity_bps=cap,
        loss_pct=loss,
        diffraction_loss_db=diffraction,
        antenna_offset_db=antenna_offset,
        noise_floor_dbm=noise_floor,
    )


def _clip(value: float, low: float, high: float) -> float:
    if not math.isfinite(value):
        return low
    if value < low:
        return low
    if value > high:
        return high
    return value
