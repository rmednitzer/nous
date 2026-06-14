"""Store-and-forward outbox with precedence triage for degraded comms (BL-077).

The comms send seam (``CommsSubsystem.tx``) is fire-and-forget: a transmission
on a link that is aged-out, forced-down, or unknown is rejected and the bytes
are gone (``bytes_accepted == 0``). ``comms_publish`` and ``self_model_publish``
encode a standards-shaped message and then meet the same wall, so a controller
that publishes during a comms blackout watches the message vanish. For an edge
appliance whose whole job is to stay legible to a controller across an
intermittent tactical link, dropping the device's own situation report the
moment comms degrade is the wrong failure mode.

This module adds the missing seam: a bounded, precedence-ordered queue that
*holds* packages the link cannot carry right now and *flushes* them in triage
order when the link recovers. It is deliberately single-hop and below the full
delay-tolerant-networking vision tracked at BL-056 (no custody transfer, no
BPv7 bundle format, no multi-hop routing or replay); it is the practical
store-and-forward and triage layer the controller needs today.

Three rules make the triage auditable:

* **Precedence first, then age.** A flush walks packages by descending military
  message precedence (FLASH before IMMEDIATE before PRIORITY before ROUTINE),
  breaking ties by enqueue order (oldest first). A scarce recovered link spends
  its budget on the most important traffic first.
* **A package is only ever dropped to make room for a strictly
  higher-precedence one.** On overflow the queue evicts the lowest-precedence,
  oldest package, but only when the arriving package outranks it; otherwise the
  arrival is refused. The queue never displaces important traffic for trivial
  traffic, and every drop is counted.
* **Stale packages expire rather than ship.** A package past its time-to-live is
  dropped (counted as ``expired``) instead of delivered, so a link that recovers
  after a long outage does not flush a backlog of outdated state -- the
  store-and-forward analogue of the SC-4 freshness gate the adapters enforce at
  encode time.

The outbox is pure and clock-injected (ADR 0019): every method that needs the
time takes ``now_s`` from the engine's simulated clock, so a scenario replays
identically. It is not thread-safe, like the rest of the single-threaded tick
loop.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..subsystems.comms import CommsSubsystem

__all__ = [
    "CommsOutbox",
    "EnqueueResult",
    "FlushResult",
    "OutboxPackage",
    "Precedence",
]


class Precedence(StrEnum):
    """Military message precedence, the triage order for a scarce link.

    Ordered ROUTINE < PRIORITY < IMMEDIATE < FLASH. The string value is the
    wire/JSON form; :meth:`rank` is the integer used for ordering and the
    eviction guard.
    """

    ROUTINE = "routine"
    PRIORITY = "priority"
    IMMEDIATE = "immediate"
    FLASH = "flash"

    def rank(self) -> int:
        return _PRECEDENCE_RANK[self]

    @classmethod
    def parse(cls, value: Any) -> Precedence:
        """Lenient parse: an unknown or missing value falls back to ROUTINE.

        A controller that fat-fingers the precedence gets the safe default (the
        lowest priority, so a typo never jumps the queue) rather than an error
        that drops the message entirely.
        """
        if isinstance(value, Precedence):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError:
                return cls.ROUTINE
        return cls.ROUTINE


_PRECEDENCE_RANK: dict[Precedence, int] = {
    Precedence.ROUTINE: 0,
    Precedence.PRIORITY: 1,
    Precedence.IMMEDIATE: 2,
    Precedence.FLASH: 3,
}


@dataclass
class OutboxPackage:
    """One queued transmission waiting for its link to carry it."""

    package_id: int
    link_id: str
    size_bytes: int
    precedence: Precedence
    kind: str
    enqueued_ts_s: float
    expiry_ts_s: float | None = None
    payload: bytes | None = None
    attempts: int = 0

    def is_expired(self, now_s: float) -> bool:
        return self.expiry_ts_s is not None and now_s >= self.expiry_ts_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "link_id": self.link_id,
            "size_bytes": self.size_bytes,
            "precedence": self.precedence.value,
            "kind": self.kind,
            "enqueued_ts_s": round(self.enqueued_ts_s, 3),
            "expiry_ts_s": (
                None if self.expiry_ts_s is None else round(self.expiry_ts_s, 3)
            ),
            "attempts": self.attempts,
        }


@dataclass
class EnqueueResult:
    """The outcome of an :meth:`CommsOutbox.enqueue` call."""

    accepted: bool
    reason: str
    package: OutboxPackage | None = None
    evicted: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "accepted": self.accepted,
            "reason": self.reason,
            "evicted": list(self.evicted),
        }
        if self.package is not None:
            body["package"] = self.package.to_dict()
        return body


@dataclass
class FlushResult:
    """What one :meth:`CommsOutbox.flush` delivered, deferred, and expired."""

    delivered: list[int] = field(default_factory=list)
    delivered_bytes: int = 0
    deferred: list[int] = field(default_factory=list)
    expired: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivered": list(self.delivered),
            "delivered_count": len(self.delivered),
            "delivered_bytes": self.delivered_bytes,
            "deferred_count": len(self.deferred),
            "expired": list(self.expired),
            "expired_count": len(self.expired),
        }


# Defaults applied when the profile carries no ``comms.outbox`` section. A
# few hundred packages and a megabyte is enough to ride a realistic blackout
# on the modelled links without letting an unbounded queue mask a wedged link.
_DEFAULT_MAX_PACKAGES = 256
_DEFAULT_MAX_BYTES = 1_048_576
_DEFAULT_TTL_S = 300.0


class CommsOutbox:
    """Bounded, precedence-ordered store-and-forward queue for outbound packages.

    Construction reads an optional ``profile["comms"]["outbox"]`` section
    (``max_packages``, ``max_bytes``, ``default_ttl_s``, ``enabled``); every
    field is coerced defensively and falls back to a safe default, mirroring how
    :class:`~nous.subsystems.comms.CommsSubsystem` reads its links. With the
    section absent the outbox runs at its defaults, so an old profile keeps
    working unchanged.
    """

    def __init__(self, profile: Mapping[str, Any] | None = None) -> None:
        cfg = _outbox_cfg(profile)
        self.enabled: bool = cfg["enabled"]
        self.max_packages: int = cfg["max_packages"]
        self.max_bytes: int = cfg["max_bytes"]
        self.default_ttl_s: float | None = cfg["default_ttl_s"]
        self._packages: list[OutboxPackage] = []
        self._next_id = 1
        self._queued_bytes = 0
        # Cumulative counters: the whole point of the queue is to make the
        # triage legible, so every disposition is tallied for the read tool.
        self.enqueued_total = 0
        self.delivered_total = 0
        self.dropped_overflow_total = 0
        self.expired_total = 0
        self.rejected_total = 0

    # -- enqueue ---------------------------------------------------------

    def enqueue(
        self,
        link_id: str,
        size_bytes: int,
        *,
        now_s: float,
        precedence: Precedence = Precedence.ROUTINE,
        kind: str = "raw",
        ttl_s: float | None = None,
        payload: bytes | None = None,
    ) -> EnqueueResult:
        """Queue a package for store-and-forward, applying the triage rules.

        Returns an :class:`EnqueueResult`: ``accepted`` is false when the
        package is empty, larger than the whole queue budget, or refused because
        the queue is full of equal-or-higher-precedence traffic. Expired
        packages are purged first, then lower-precedence packages are evicted
        (oldest first) only while the arrival strictly outranks them.
        """
        if not self.enabled:
            return EnqueueResult(False, "outbox disabled")
        size = int(size_bytes)
        if size <= 0:
            return EnqueueResult(False, "non-positive size")
        if size > self.max_bytes:
            self.rejected_total += 1
            return EnqueueResult(
                False, f"package size {size} exceeds outbox max_bytes {self.max_bytes}"
            )

        self._purge_expired(now_s)

        pkg = OutboxPackage(
            package_id=self._next_id,
            link_id=link_id,
            size_bytes=size,
            precedence=precedence,
            kind=kind,
            enqueued_ts_s=float(now_s),
            expiry_ts_s=self._resolve_expiry(now_s, ttl_s),
            payload=payload,
        )

        evicted: list[int] = []
        while not self._fits(pkg):
            victim = self._evict_candidate(pkg.precedence.rank())
            if victim is None:
                self.rejected_total += 1
                return EnqueueResult(
                    False,
                    "outbox full; no lower-precedence package to evict",
                    evicted=evicted,
                )
            self._remove(victim)
            self.dropped_overflow_total += 1
            evicted.append(victim.package_id)

        self._next_id += 1
        self._packages.append(pkg)
        self._queued_bytes += pkg.size_bytes
        self.enqueued_total += 1
        return EnqueueResult(True, "enqueued", package=pkg, evicted=evicted)

    # -- flush -----------------------------------------------------------

    def flush(
        self,
        comms: CommsSubsystem,
        *,
        now_s: float,
        link_budget_bytes: Mapping[str, float] | None = None,
    ) -> FlushResult:
        """Deliver queued packages in triage order against the live links.

        Expired packages are dropped first. The remaining packages are walked
        by descending precedence then enqueue order; each is delivered through
        ``comms.tx`` when its link is live and the per-link byte budget (if any)
        still has room. A package whose link is down, or that does not fit the
        remaining budget, stays queued -- and once a package for a link cannot
        be sent, that link is closed for the rest of this flush so a smaller,
        lower-precedence package never jumps ahead of it.

        ``link_budget_bytes`` caps the bytes delivered per link this call; a
        link absent from the mapping (or the whole mapping being ``None``) is
        unbounded. The tick-driven flush passes each link's per-tick capacity so
        a slow recovered link drains at its modelled rate.
        """
        result = FlushResult()
        for pkg in self._expired(now_s):
            self._remove(pkg)
            self.expired_total += 1
            result.expired.append(pkg.package_id)

        remaining: dict[str, float] = {}
        closed: set[str] = set()

        def budget_for(link_id: str) -> float:
            if link_budget_bytes is None or link_id not in link_budget_bytes:
                return float("inf")
            if link_id not in remaining:
                remaining[link_id] = max(0.0, float(link_budget_bytes[link_id]))
            return remaining[link_id]

        for pkg in self._triage_order():
            if pkg.link_id in closed:
                result.deferred.append(pkg.package_id)
                continue
            link = comms.link(pkg.link_id)
            if link is None or not link.is_live():
                pkg.attempts += 1
                closed.add(pkg.link_id)
                result.deferred.append(pkg.package_id)
                continue
            if pkg.size_bytes > budget_for(pkg.link_id):
                closed.add(pkg.link_id)
                result.deferred.append(pkg.package_id)
                continue
            accepted = comms.tx(pkg.link_id, pkg.size_bytes)
            if accepted <= 0:
                pkg.attempts += 1
                closed.add(pkg.link_id)
                result.deferred.append(pkg.package_id)
                continue
            self._remove(pkg)
            self.delivered_total += 1
            result.delivered.append(pkg.package_id)
            result.delivered_bytes += accepted
            if pkg.link_id in remaining:
                remaining[pkg.link_id] -= accepted
        return result

    def flush_tick(
        self, comms: CommsSubsystem, dt: float, now_s: float
    ) -> FlushResult:
        """Best-effort per-tick drain at each link's modelled capacity.

        Called from the engine tick after the comms subsystem has stepped, so a
        link that recovered this tick drains immediately. The per-link budget is
        ``bandwidth_bps * dt / 8`` bytes, which rate-limits a slow link (a
        recovered LoRa link clears a few kilobytes a tick, not its whole
        backlog) while a fat link clears everything that fits.
        """
        if not self.enabled or not self._packages:
            # Still purge expiry so a disabled-after-fill or idle outbox does
            # not retain stale packages indefinitely.
            result = FlushResult()
            for pkg in self._expired(now_s):
                self._remove(pkg)
                self.expired_total += 1
                result.expired.append(pkg.package_id)
            return result
        budget: dict[str, float] = {
            link.link_id: link_per_tick_budget(link.bandwidth_bps, dt) for link in comms
        }
        return self.flush(comms, now_s=now_s, link_budget_bytes=budget)

    # -- reads -----------------------------------------------------------

    def depth(self) -> int:
        return len(self._packages)

    def queued_bytes(self) -> int:
        return self._queued_bytes

    def by_precedence(self) -> dict[str, int]:
        counts = {p.value: 0 for p in Precedence}
        for pkg in self._packages:
            counts[pkg.precedence.value] += 1
        return counts

    def by_link(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for pkg in self._packages:
            counts[pkg.link_id] = counts.get(pkg.link_id, 0) + 1
        return counts

    def head(self) -> OutboxPackage | None:
        """The package a flush would deliver first (highest precedence, oldest)."""
        order = self._triage_order()
        return order[0] if order else None

    def packages(self) -> list[OutboxPackage]:
        """Snapshot of queued packages in triage (flush) order."""
        return self._triage_order()

    def status(self, now_s: float | None = None) -> dict[str, Any]:
        """The read surface for the ``comms_outbox`` tool.

        ``now_s`` (when supplied) is used only to report the head package's
        remaining time-to-live; it does not mutate the queue.
        """
        head = self.head()
        head_body: dict[str, Any] | None = None
        if head is not None:
            head_body = head.to_dict()
            if now_s is not None and head.expiry_ts_s is not None:
                head_body["ttl_remaining_s"] = round(
                    max(0.0, head.expiry_ts_s - now_s), 3
                )
        return {
            "enabled": self.enabled,
            "depth": self.depth(),
            "queued_bytes": self.queued_bytes(),
            "max_packages": self.max_packages,
            "max_bytes": self.max_bytes,
            "by_precedence": self.by_precedence(),
            "by_link": self.by_link(),
            "head": head_body,
            "counters": {
                "enqueued": self.enqueued_total,
                "delivered": self.delivered_total,
                "dropped_overflow": self.dropped_overflow_total,
                "expired": self.expired_total,
                "rejected": self.rejected_total,
            },
        }

    # -- internals -------------------------------------------------------

    def _resolve_expiry(self, now_s: float, ttl_s: float | None) -> float | None:
        effective = ttl_s if ttl_s is not None else self.default_ttl_s
        if effective is None:
            return None
        try:
            ttl = float(effective)
        except (TypeError, ValueError):
            return None
        if ttl <= 0.0:
            return None
        return float(now_s) + ttl

    def _fits(self, pkg: OutboxPackage) -> bool:
        return (
            len(self._packages) + 1 <= self.max_packages
            and self._queued_bytes + pkg.size_bytes <= self.max_bytes
        )

    def _evict_candidate(self, below_rank: int) -> OutboxPackage | None:
        """Lowest-precedence, oldest package whose rank is strictly below ``below_rank``."""
        candidate: OutboxPackage | None = None
        for pkg in self._packages:
            if pkg.precedence.rank() >= below_rank:
                continue
            if candidate is None or (
                pkg.precedence.rank(),
                pkg.enqueued_ts_s,
                pkg.package_id,
            ) < (
                candidate.precedence.rank(),
                candidate.enqueued_ts_s,
                candidate.package_id,
            ):
                candidate = pkg
        return candidate

    def _triage_order(self) -> list[OutboxPackage]:
        return sorted(
            self._packages,
            key=lambda p: (-p.precedence.rank(), p.enqueued_ts_s, p.package_id),
        )

    def _expired(self, now_s: float) -> list[OutboxPackage]:
        return [pkg for pkg in self._packages if pkg.is_expired(now_s)]

    def _purge_expired(self, now_s: float) -> None:
        for pkg in self._expired(now_s):
            self._remove(pkg)
            self.expired_total += 1

    def _remove(self, pkg: OutboxPackage) -> None:
        self._packages.remove(pkg)
        self._queued_bytes -= pkg.size_bytes


def _outbox_cfg(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Coerce the optional ``comms.outbox`` profile section to safe values."""
    section: Mapping[str, Any] = {}
    if isinstance(profile, Mapping):
        comms = profile.get("comms")
        if isinstance(comms, Mapping):
            raw = comms.get("outbox")
            if isinstance(raw, Mapping):
                section = raw
    return {
        "enabled": _coerce_bool(section.get("enabled"), default=True),
        "max_packages": _coerce_positive_int(
            section.get("max_packages"), _DEFAULT_MAX_PACKAGES
        ),
        "max_bytes": _coerce_positive_int(section.get("max_bytes"), _DEFAULT_MAX_BYTES),
        "default_ttl_s": _coerce_ttl(section.get("default_ttl_s"), _DEFAULT_TTL_S),
    }


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _coerce_positive_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        out = int(value)
    except (TypeError, ValueError):
        return fallback
    return out if out > 0 else fallback


def _coerce_ttl(value: Any, fallback: float | None) -> float | None:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return fallback
    try:
        out = float(value)
    except (TypeError, ValueError):
        return fallback
    if out <= 0.0:
        return None
    return out


def link_per_tick_budget(bandwidth_bps: float, dt_s: float) -> float:
    """Bytes a link can carry in one tick at its nominal bandwidth.

    Exposed for the flush tool and tests so the per-tick rate-limit is computed
    one way everywhere.
    """
    return max(0.0, float(bandwidth_bps) * float(dt_s) / 8.0)
