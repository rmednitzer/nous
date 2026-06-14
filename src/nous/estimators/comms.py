"""Comms estimator: per-link Sequential Importance Resampling particle filter (BL-030).

Each tracked link carries a small ensemble of binary-state particles
representing whether the link is *actually* carrying packets. The hidden
state is sticky (a connected link tends to stay connected for many ticks;
a disconnected one tends to stay down) and the transition probabilities
depend on the latest RSSI and packet-loss observation. The observation
model treats throughput as the strongest evidence: zero throughput
strongly favours the disconnected hypothesis, profile-class throughput
strongly favours the connected one.

The filter exposes the same public surface as the v0.1 stub
(:meth:`update`, :meth:`predict`, :meth:`state`, :meth:`links`) so the
engine wiring is unchanged. The aggregate :class:`~nous.types.Estimate`
now carries a real variance for ``connected_links`` derived from the
particle ensemble rather than a fixed sigma.

The filter is seeded deterministically (``seed=`` argument, default
``0``) so tests can assert exact particle trajectories under ADR-0019.
``numpy.random.default_rng`` is the entropy source; that keeps the seam
compatible with the engine-wide RNG handle the deterministic-seed ADR
plans to thread through subsystems.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np

from ..types import Estimate, EstimatorHealth, LinkEstimate, Observation

__all__ = ["CommsParticleFilter", "LinkBelief"]


_LIVE_THROUGHPUT_FLOOR_BPS = 1.0
_DEFAULT_PARTICLES = 64
# Sticky-Markov stickiness bounds. Both stay_connected and stay_disconnected
# sweep the single interval [0.93, 0.97] as quality runs worst -> best, in
# opposite directions (see _transition_probabilities), so these are shared
# max / min bounds, not per-state baselines despite the names. The max (0.97)
# is stay_connected at best quality and stay_disconnected at worst; the min
# (0.93) is stay_connected at worst quality and stay_disconnected at best. A
# connected link is thus stickiest on a good channel, a disconnected link on a
# bad one (audit 2026-06-14b M-4).
_STAY_CONNECTED_BASE = 0.97  # shared upper bound (max stickiness)
_STAY_DISCONNECTED_BASE = 0.93  # shared lower bound (min stickiness)
_RSSI_GOOD_DBM = -80.0
_RSSI_BAD_DBM = -105.0
_LOSS_GOOD_PCT = 5.0
_LOSS_BAD_PCT = 60.0
_THROUGHPUT_FLOOR_BPS = 1.0
_THROUGHPUT_OBS_SIGMA_FRAC = 0.25
_LIKELIHOOD_FLOOR = 1e-6


class LinkBelief:
    """One link's particle ensemble plus the latest observation channels."""

    __slots__ = (
        "_rng",
        "capacity_bps",
        "collapses",
        "expected_throughput_bps",
        "link_id",
        "loss_pct",
        "particles",
        "rssi_dbm",
        "throughput_bps",
        "weights",
    )

    def __init__(
        self,
        link_id: str,
        *,
        n_particles: int,
        rng: np.random.Generator,
    ) -> None:
        self.link_id = link_id
        half = n_particles // 2
        connected_count = max(1, half)
        disconnected_count = max(1, n_particles - connected_count)
        self.particles: np.ndarray = np.concatenate(
            [
                np.ones(connected_count, dtype=np.int8),
                np.zeros(disconnected_count, dtype=np.int8),
            ]
        )
        size = self.particles.size
        self.weights: np.ndarray = np.full(size, 1.0 / size)
        self.rssi_dbm = -100.0
        self.loss_pct = 0.0
        self.throughput_bps = 0.0
        self.expected_throughput_bps = 0.0
        self.capacity_bps = 0.0
        self.collapses = 0
        self._rng = rng

    def belief(self) -> float:
        """Probability the link is connected (weighted mean over particles)."""
        if self.particles.size == 0:
            return 0.0
        return float(np.sum(self.weights * self.particles))

    def variance(self) -> float:
        """Posterior variance of the connected-probability ensemble."""
        if self.particles.size <= 1:
            return 0.0
        mean = self.belief()
        return float(np.sum(self.weights * (self.particles - mean) ** 2))

    def predict(self) -> None:
        """Markov transition: each particle flips with channel-conditioned prob."""
        stay_c, stay_d = _transition_probabilities(self.rssi_dbm, self.loss_pct)
        u = self._rng.random(self.particles.size)
        stay = np.where(self.particles == 1, stay_c, stay_d)
        flips = u >= stay
        self.particles = np.where(flips, 1 - self.particles, self.particles).astype(
            np.int8
        )

    def update_observation(
        self,
        *,
        rssi_dbm: float,
        loss_pct: float,
        throughput_bps: float,
        expected_throughput_bps: float,
        capacity_bps: float = 0.0,
        observed_connected_flag: bool,
    ) -> None:
        """Weight particles by likelihood of the observation, then resample."""
        self.rssi_dbm = rssi_dbm
        self.loss_pct = max(0.0, min(100.0, loss_pct))
        self.throughput_bps = max(0.0, throughput_bps)
        self.expected_throughput_bps = max(_THROUGHPUT_FLOOR_BPS, expected_throughput_bps)
        self.capacity_bps = max(0.0, capacity_bps)

        likelihood_connected = _likelihood_given_connected(
            self.throughput_bps,
            self.expected_throughput_bps,
            self.loss_pct,
            observed_connected_flag,
        )
        likelihood_disconnected = _likelihood_given_disconnected(
            self.throughput_bps,
            self.loss_pct,
            observed_connected_flag,
        )
        likelihoods = np.where(
            self.particles == 1, likelihood_connected, likelihood_disconnected
        )
        new_weights = self.weights * likelihoods
        total = float(np.sum(new_weights))
        if total <= 0.0 or not math.isfinite(total):
            # Degenerate likelihood: the ensemble carries no information about
            # this observation. Reset to a uniform prior and count it, the
            # particle-filter analog of a covariance reset.
            self.collapses += 1
            self.weights.fill(1.0 / self.weights.size)
        else:
            self.weights = new_weights / total
            if _effective_sample_size(self.weights) < self.weights.size / 2.0:
                self._resample()

    def _resample(self) -> None:
        """Systematic resampling: low-variance, deterministic for tests."""
        n = self.particles.size
        positions = (np.arange(n) + self._rng.random()) / n
        cumulative = np.cumsum(self.weights)
        cumulative[-1] = 1.0
        indices = np.searchsorted(cumulative, positions)
        indices = np.clip(indices, 0, n - 1)
        self.particles = self.particles[indices].copy()
        self.weights = np.full(n, 1.0 / n)


class CommsParticleFilter:
    """Per-link SIR particle filter + connected-count aggregate (BL-030)."""

    name: str = "comms"

    def __init__(
        self,
        particles: int = _DEFAULT_PARTICLES,
        *,
        seed: int = 0,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._t = 0.0
        self._particles = max(2, int(particles))
        # ADR 0019: prefer an explicit RNG injected by the engine so
        # determinism is centralised through ``Engine(seed=...)``;
        # fall back to ``seed`` for tests and standalone use that
        # construct the filter directly.
        self._rng = rng if rng is not None else np.random.default_rng(int(seed))
        self._links: dict[str, LinkBelief] = {}
        self._link_estimates: dict[str, LinkEstimate] = {}
        self._last_update_healthy = True

    @property
    def particles(self) -> int:
        return self._particles

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        for belief in self._links.values():
            belief.predict()

    def update(self, obs: Observation) -> None:
        collapses_before = sum(b.collapses for b in self._links.values())
        seen: set[str] = set()
        for entry in obs.payload.get("links") or []:
            if not isinstance(entry, dict):
                continue
            link_id = entry.get("link_id")
            if not isinstance(link_id, str) or not link_id:
                continue
            try:
                rssi = float(entry.get("rssi_dbm", -120.0))
                loss = float(entry.get("loss_pct", 100.0))
                throughput = float(entry.get("throughput_bps", 0.0))
                capacity = float(entry.get("capacity_bps", 0.0))
            except (TypeError, ValueError):
                continue
            connected_flag = bool(entry.get("connected", False))
            seen.add(link_id)

            belief = self._links.get(link_id)
            if belief is None:
                belief = LinkBelief(
                    link_id,
                    n_particles=self._particles,
                    rng=self._rng,
                )
                self._links[link_id] = belief

            # BL-048 / ADR 0053: when the observation carries a modeled capacity,
            # the expected throughput is that capacity, so an observed rate far
            # below capacity lowers the connected likelihood. Without a capacity
            # channel the filter keeps the self-referential floor (ADR 0051's
            # documented scale-insensitivity), so manual observations are
            # unaffected.
            if capacity > _THROUGHPUT_FLOOR_BPS:
                expected_throughput = capacity
            else:
                expected_throughput = max(throughput, _THROUGHPUT_FLOOR_BPS)
            belief.update_observation(
                rssi_dbm=rssi,
                loss_pct=loss,
                throughput_bps=throughput,
                expected_throughput_bps=expected_throughput,
                capacity_bps=capacity,
                observed_connected_flag=connected_flag,
            )
            self._link_estimates[link_id] = _link_estimate_from_belief(belief)

        for missing in set(self._links) - seen:
            self._link_estimates.setdefault(
                missing, _link_estimate_from_belief(self._links[missing])
            )

        collapses_after = sum(b.collapses for b in self._links.values())
        self._last_update_healthy = collapses_after == collapses_before

        try:
            ts = float(obs.ts_s)
        except (TypeError, ValueError):
            return
        if math.isfinite(ts) and ts >= 0.0:
            self._t = ts

    def links(self) -> list[LinkEstimate]:
        return [self._link_estimates[link_id] for link_id in self._links]

    def belief(self, link_id: str) -> float | None:
        """Return the posterior P(connected) for ``link_id`` or ``None``."""
        belief = self._links.get(link_id)
        return belief.belief() if belief is not None else None

    def health(self) -> EstimatorHealth:
        """Filter health from particle-weight collapse.

        A non-Gaussian filter has no innovation test ratio, so the health
        block reports the events that matter for a particle ensemble: a
        weight collapse to the uniform prior (the reset-count) and whether the
        most recent update suffered one (the health flag).
        """
        resets = sum(b.collapses for b in self._links.values())
        return EstimatorHealth(
            healthy=self._last_update_healthy,
            fused=bool(self._links),
            reset_count=resets,
        )

    def state(self) -> Estimate:
        connected_count = 0
        belief_sum = 0.0
        variance_sum = 0.0
        for belief in self._links.values():
            est = self._link_estimates.get(belief.link_id)
            if est is not None and est.connected:
                connected_count += 1
            belief_sum += belief.belief()
            variance_sum += belief.variance()
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={
                "connected_links": float(connected_count),
                "total_links": float(len(self._links)),
                "connected_links_belief": belief_sum,
            },
            covariance={
                "connected_links": variance_sum,
                "total_links": 0.0,
                "connected_links_belief": variance_sum,
            },
            health=self.health(),
        )


def _link_estimate_from_belief(belief: LinkBelief) -> LinkEstimate:
    connected = belief.belief() >= 0.5 and belief.throughput_bps >= _LIVE_THROUGHPUT_FLOOR_BPS
    return LinkEstimate(
        link_id=belief.link_id,
        connected=connected,
        rssi_dbm=belief.rssi_dbm,
        loss_pct=belief.loss_pct,
        throughput_bps=belief.throughput_bps if connected else 0.0,
        capacity_bps=belief.capacity_bps if connected else 0.0,
    )


def _transition_probabilities(rssi_dbm: float, loss_pct: float) -> tuple[float, float]:
    """Sticky Markov transition probabilities given the latest channel state.

    Returns ``(stay_connected, stay_disconnected)``. A bad RSSI / high loss
    pulls the connected hypothesis toward flipping; a good RSSI / low loss
    pulls the disconnected hypothesis toward flipping.
    """
    rssi_signal = _clip01(
        (rssi_dbm - _RSSI_BAD_DBM) / (_RSSI_GOOD_DBM - _RSSI_BAD_DBM)
    )
    loss_signal = 1.0 - _clip01(
        (loss_pct - _LOSS_GOOD_PCT) / (_LOSS_BAD_PCT - _LOSS_GOOD_PCT)
    )
    quality = 0.5 * (rssi_signal + loss_signal)
    stay_connected = _STAY_DISCONNECTED_BASE + quality * (
        _STAY_CONNECTED_BASE - _STAY_DISCONNECTED_BASE
    )
    stay_disconnected = _STAY_CONNECTED_BASE - quality * (
        _STAY_CONNECTED_BASE - _STAY_DISCONNECTED_BASE
    )
    return stay_connected, stay_disconnected


def _likelihood_given_connected(
    throughput_bps: float,
    expected_throughput_bps: float,
    loss_pct: float,
    flag: bool,
) -> float:
    """P(observation | actually connected). Gaussian on log-throughput residual."""
    if throughput_bps <= _THROUGHPUT_FLOOR_BPS:
        return _LIKELIHOOD_FLOOR
    log_obs = math.log(max(throughput_bps, _THROUGHPUT_FLOOR_BPS))
    log_exp = math.log(max(expected_throughput_bps, _THROUGHPUT_FLOOR_BPS))
    # ``_THROUGHPUT_OBS_SIGMA_FRAC`` is the constant log-space observation sigma
    # (a unitless standard deviation) that normalizes the log residual into a
    # z-score. The earlier ``_THROUGHPUT_OBS_SIGMA_FRAC * max(expected, 1.0)``
    # numerator and ``/ max(expected, 1.0)`` divisor always cancelled to exactly
    # this constant (audit 2026-06-14 COMMS-4), so the log-space spread is a
    # deliberate constant rather than a scale-dependent one.
    z = (log_obs - log_exp) / _THROUGHPUT_OBS_SIGMA_FRAC
    base = math.exp(-0.5 * z * z)
    loss_factor = max(0.0, 1.0 - loss_pct / 100.0)
    flag_factor = 1.0 if flag else 0.6
    return max(base * loss_factor * flag_factor, _LIKELIHOOD_FLOOR)


def _likelihood_given_disconnected(
    throughput_bps: float,
    loss_pct: float,
    flag: bool,
) -> float:
    """P(observation | actually disconnected). Concentrated at zero throughput."""
    if throughput_bps <= _THROUGHPUT_FLOOR_BPS:
        base = 1.0
    else:
        base = math.exp(-throughput_bps / max(_THROUGHPUT_FLOOR_BPS, 1.0))
    loss_factor = 0.5 + 0.5 * (loss_pct / 100.0)
    flag_factor = 1.0 if not flag else 0.5
    return max(base * loss_factor * flag_factor, _LIKELIHOOD_FLOOR)


def _effective_sample_size(weights: np.ndarray) -> float:
    s2 = float(np.sum(weights * weights))
    if s2 <= 0.0:
        return 0.0
    return 1.0 / s2


def _clip01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _ts_finite(items: Iterable[float]) -> float | None:
    """Helper retained for compatibility with legacy callers; ignores NaN."""
    for v in items:
        if math.isfinite(v):
            return v
    return None
