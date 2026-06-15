"""Multi-node DTN mesh with custody transfer (BL-056 increment 2, ADR 0062).

The BL-077 outbox is the device's direct-link egress buffer. This module is the
delay-tolerant-networking overlay above it: a configured graph of nodes (the
device plus abstract peers) connected by contacts, across which bundles are
routed hop by hop toward a destination endpoint, stored and forwarded at each hop
when a contact is down, and held under custody for reliable delivery.

The device is the ``self`` node; peer nodes are hold-and-forward stores with no
subsystem physics, the same way BL-048 models a link's far peer as a position
rather than a second device. The topology is an optional ``dtn`` profile section,
so a profile without it leaves the mesh empty and inert. The mesh is pure and
clock/RNG-injected (ADR 0019): ``step`` takes the simulated time and the loss
draw uses the engine RNG, so a seeded scenario replays identically.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np

from .comms_outbox import Precedence, link_per_tick_budget

__all__ = ["BundleState", "Contact", "DtnMesh", "DtnNode", "MeshBundle"]

_DEFAULT_RATE_BPS = 1_000_000.0
_DEFAULT_CUSTODY_RETRIES = 8
_DEFAULT_LIFETIME_S = 600.0
# Routing-loop guard: a bundle that has been forwarded this many hops without
# reaching its destination is dropped rather than circulating forever.
_MAX_HOPS = 32


class BundleState(StrEnum):
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXPIRED = "expired"
    DROPPED = "dropped"


@dataclass
class Contact:
    """A bidirectional link between two mesh nodes."""

    a: str
    b: str
    up: bool = True
    rate_bps: float = _DEFAULT_RATE_BPS
    loss_pct: float = 0.0

    def connects(self, x: str, y: str) -> bool:
        return {self.a, self.b} == {x, y}


@dataclass
class MeshBundle:
    """A bundle in transit across the mesh (BPv7 identity per ADR 0061)."""

    bundle_id: str
    source_eid: str
    dest_eid: str
    sequence: int
    size_bytes: int
    precedence: Precedence
    created_ts_s: float
    expiry_ts_s: float | None
    custody: bool
    holder_eid: str
    hops: int = 0
    attempts: int = 0
    state: BundleState = BundleState.IN_TRANSIT

    def is_expired(self, now_s: float) -> bool:
        return self.expiry_ts_s is not None and now_s >= self.expiry_ts_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "source_eid": self.source_eid,
            "dest_eid": self.dest_eid,
            "holder_eid": self.holder_eid,
            "size_bytes": self.size_bytes,
            "precedence": self.precedence.value,
            "custody": self.custody,
            "hops": self.hops,
            "attempts": self.attempts,
            "state": self.state.value,
            "created_ts_s": round(self.created_ts_s, 3),
            "expiry_ts_s": (
                None if self.expiry_ts_s is None else round(self.expiry_ts_s, 3)
            ),
        }


@dataclass
class DtnNode:
    """A mesh node: an EID and the bundles it currently holds."""

    eid: str
    store: list[MeshBundle] = field(default_factory=list)


class DtnMesh:
    """A configured multi-node DTN with shortest-path routing and custody."""

    def __init__(
        self,
        profile: Mapping[str, Any] | None = None,
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        cfg = _mesh_cfg(profile)
        self.enabled: bool = cfg["enabled"]
        self.self_eid: str = cfg["self_eid"]
        self.custody_retries: int = cfg["custody_retries"]
        self.default_lifetime_s: float = cfg["default_lifetime_s"]
        self._rng = rng
        self.nodes: dict[str, DtnNode] = {
            eid: DtnNode(eid) for eid in cfg["node_eids"]
        }
        self.contacts: list[Contact] = cfg["contacts"]
        self._next_seq = 1
        self.originated_total = 0
        self.delivered_total = 0
        self.forwarded_total = 0
        self.retransmits_total = 0
        self.dropped_total = 0
        self.expired_total = 0

    # -- origination -------------------------------------------------------

    def originate(
        self,
        dest_eid: str,
        size_bytes: int,
        *,
        now_s: float,
        precedence: Precedence = Precedence.ROUTINE,
        custody: bool = False,
        lifetime_s: float | None = None,
        bundle_id: str | None = None,
    ) -> MeshBundle | None:
        """Create a bundle at the device node bound for ``dest_eid``.

        Returns the bundle, or ``None`` when the mesh is disabled or the size is
        non-positive. ``custody=True`` requests reliable delivery: the bundle is
        retained and retransmitted on a lost forward instead of dropped.
        """
        if not self.enabled or int(size_bytes) <= 0:
            return None
        sequence = self._next_seq
        if isinstance(bundle_id, str) and bundle_id.strip() != "":
            bid = bundle_id.strip()
        else:
            bid = f"{self.self_eid.rstrip('/')}/{sequence}"
        lifetime = lifetime_s if lifetime_s is not None else self.default_lifetime_s
        expiry = (
            float(now_s) + lifetime if lifetime is not None and lifetime > 0.0 else None
        )
        bundle = MeshBundle(
            bundle_id=bid,
            source_eid=self.self_eid,
            dest_eid=dest_eid,
            sequence=sequence,
            size_bytes=int(size_bytes),
            precedence=precedence,
            created_ts_s=float(now_s),
            expiry_ts_s=expiry,
            custody=bool(custody),
            holder_eid=self.self_eid,
        )
        self._next_seq += 1
        self.originated_total += 1
        if dest_eid == self.self_eid:
            bundle.state = BundleState.DELIVERED
            self.delivered_total += 1
        else:
            self.nodes[self.self_eid].store.append(bundle)
        return bundle

    # -- routing -----------------------------------------------------------

    def next_hop(self, src_eid: str, dest_eid: str) -> tuple[str, Contact] | None:
        """The first hop on a shortest path over up-contacts, or ``None``.

        Breadth-first over the currently-up contact subgraph; ties are broken by
        neighbour EID so the route is deterministic.
        """
        if (
            src_eid == dest_eid
            or src_eid not in self.nodes
            or dest_eid not in self.nodes
        ):
            return None
        adj = self._adjacency_up()
        prev: dict[str, tuple[str, Contact]] = {}
        seen = {src_eid}
        queue = deque([src_eid])
        while queue:
            node = queue.popleft()
            if node == dest_eid:
                break
            for nbr, contact in sorted(adj[node], key=lambda t: t[0]):
                if nbr in seen:
                    continue
                seen.add(nbr)
                prev[nbr] = (node, contact)
                queue.append(nbr)
        if dest_eid not in prev:
            return None
        cur = dest_eid
        while prev[cur][0] != src_eid:
            cur = prev[cur][0]
        return (cur, prev[cur][1])

    def _adjacency_up(self) -> dict[str, list[tuple[str, Contact]]]:
        adj: dict[str, list[tuple[str, Contact]]] = {eid: [] for eid in self.nodes}
        for c in self.contacts:
            if not c.up or c.a not in self.nodes or c.b not in self.nodes:
                continue
            adj[c.a].append((c.b, c))
            adj[c.b].append((c.a, c))
        return adj

    # -- step --------------------------------------------------------------

    def step(self, dt: float, now_s: float) -> None:
        """Advance the mesh one tick: expire, then route each bundle one hop."""
        if not self.enabled:
            return
        self._expire(now_s)
        budget: dict[frozenset[str], float] = {}
        moved: set[int] = set()
        for eid in sorted(self.nodes):
            node = self.nodes[eid]
            for bundle in self._triage(node.store):
                if id(bundle) in moved:
                    continue
                hop = self.next_hop(eid, bundle.dest_eid)
                if hop is None:
                    continue
                next_eid, contact = hop
                key = frozenset({contact.a, contact.b})
                if key not in budget:
                    budget[key] = link_per_tick_budget(contact.rate_bps, dt)
                if bundle.size_bytes > budget[key]:
                    continue
                if self._forward_lost(contact):
                    bundle.attempts += 1
                    if bundle.custody and bundle.attempts <= self.custody_retries:
                        self.retransmits_total += 1
                    else:
                        self._drop(node, bundle)
                    continue
                budget[key] -= bundle.size_bytes
                node.store.remove(bundle)
                bundle.holder_eid = next_eid
                bundle.hops += 1
                self.forwarded_total += 1
                moved.add(id(bundle))
                if next_eid == bundle.dest_eid:
                    bundle.state = BundleState.DELIVERED
                    self.delivered_total += 1
                elif bundle.hops > _MAX_HOPS:
                    bundle.state = BundleState.DROPPED
                    self.dropped_total += 1
                else:
                    self.nodes[next_eid].store.append(bundle)

    def _forward_lost(self, contact: Contact) -> bool:
        if self._rng is None:
            return False
        loss = max(0.0, min(100.0, float(contact.loss_pct)))
        if loss <= 0.0:
            return False
        return float(self._rng.random()) < loss / 100.0

    def _expire(self, now_s: float) -> None:
        for node in self.nodes.values():
            for bundle in [b for b in node.store if b.is_expired(now_s)]:
                node.store.remove(bundle)
                bundle.state = BundleState.EXPIRED
                self.expired_total += 1

    def _drop(self, node: DtnNode, bundle: MeshBundle) -> None:
        node.store.remove(bundle)
        bundle.state = BundleState.DROPPED
        self.dropped_total += 1

    @staticmethod
    def _triage(store: list[MeshBundle]) -> list[MeshBundle]:
        return sorted(
            store,
            key=lambda b: (-b.precedence.rank(), b.created_ts_s, b.sequence),
        )

    # -- control + reads ---------------------------------------------------

    def set_contact(
        self,
        a: str,
        b: str,
        *,
        up: bool | None = None,
        loss_pct: float | None = None,
        rate_bps: float | None = None,
    ) -> bool:
        """Override a contact's state (a scenario / engine seam). False if absent."""
        for c in self.contacts:
            if c.connects(a, b):
                if up is not None:
                    c.up = bool(up)
                if loss_pct is not None:
                    c.loss_pct = max(0.0, min(100.0, float(loss_pct)))
                if rate_bps is not None:
                    c.rate_bps = max(0.0, float(rate_bps))
                return True
        return False

    def in_transit(self) -> list[MeshBundle]:
        return [b for eid in sorted(self.nodes) for b in self.nodes[eid].store]

    def status(self) -> dict[str, Any]:
        """The read surface for the ``dtn_mesh`` tool."""
        return {
            "enabled": self.enabled,
            "self_eid": self.self_eid,
            "nodes": [
                {"eid": eid, "held": len(self.nodes[eid].store)}
                for eid in sorted(self.nodes)
            ],
            "contacts": [
                {
                    "a": c.a,
                    "b": c.b,
                    "up": c.up,
                    "rate_bps": c.rate_bps,
                    "loss_pct": c.loss_pct,
                }
                for c in self.contacts
            ],
            "in_transit": len(self.in_transit()),
            "counters": {
                "originated": self.originated_total,
                "delivered": self.delivered_total,
                "forwarded": self.forwarded_total,
                "retransmits": self.retransmits_total,
                "dropped": self.dropped_total,
                "expired": self.expired_total,
            },
        }


def _mesh_cfg(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Coerce the optional ``dtn`` profile section to safe values."""
    section: Mapping[str, Any] = {}
    name = "nous-node"
    if isinstance(profile, Mapping):
        raw_name = profile.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            name = raw_name.strip()
        dtn = profile.get("dtn")
        if isinstance(dtn, Mapping):
            section = dtn

    self_eid = _str_or(section.get("self_eid"), f"dtn://{name}/")
    contacts = _parse_contacts(section.get("contacts"))
    node_eids: set[str] = {self_eid}
    raw_nodes = section.get("nodes")
    if isinstance(raw_nodes, (list, tuple)):
        for entry in raw_nodes:
            if isinstance(entry, str) and entry.strip():
                node_eids.add(entry.strip())
    for c in contacts:
        node_eids.add(c.a)
        node_eids.add(c.b)

    return {
        "enabled": _coerce_bool(section.get("enabled"), default=bool(section)),
        "self_eid": self_eid,
        "node_eids": node_eids,
        "contacts": contacts,
        "custody_retries": _positive_int(
            section.get("custody_retries"), _DEFAULT_CUSTODY_RETRIES
        ),
        "default_lifetime_s": _positive_float(
            section.get("default_lifetime_s"), _DEFAULT_LIFETIME_S
        ),
    }


def _parse_contacts(raw: Any) -> list[Contact]:
    contacts: list[Contact] = []
    if not isinstance(raw, (list, tuple)):
        return contacts
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        a = entry.get("a")
        b = entry.get("b")
        if not (isinstance(a, str) and a.strip() and isinstance(b, str) and b.strip()):
            continue
        contacts.append(
            Contact(
                a=a.strip(),
                b=b.strip(),
                up=_coerce_bool(entry.get("up"), default=True),
                rate_bps=_positive_float(entry.get("rate_bps"), _DEFAULT_RATE_BPS),
                loss_pct=max(0.0, min(100.0, _positive_float(entry.get("loss_pct"), 0.0))),
            )
        )
    return contacts


def _str_or(value: Any, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _coerce_bool(value: Any, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _positive_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        out = int(value)
    except (TypeError, ValueError):
        return fallback
    return out if out > 0 else fallback


def _positive_float(value: Any, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    try:
        out = float(value)
    except (TypeError, ValueError):
        return fallback
    return out if out >= 0.0 else fallback
