"""Multi-node DTN mesh: contact-graph routing, store-and-forward, custody.

BL-056 / ADR 0062 (mesh core) and ADR 0063 (contact-graph routing, custody ack).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from nous.state.dtn_mesh import BundleState, DtnMesh, MeshBundle, _RecentIds


def _mesh(dtn: dict[str, Any], *, rng: np.random.Generator | None = None) -> DtnMesh:
    return DtnMesh({"name": "test", "dtn": dtn}, rng=rng)


def _state(bundle: MeshBundle) -> BundleState:
    """Read the mutable bundle state without tripping mypy's flow narrowing."""
    return bundle.state


def test_disabled_without_a_dtn_section() -> None:
    mesh = DtnMesh({"name": "test"})
    assert mesh.enabled is False
    assert mesh.originate("dtn://ground/", 100, now_s=0.0) is None


def test_direct_delivery_in_one_hop() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [{"a": "dtn://dev/", "b": "dtn://ground/"}],
        }
    )
    assert mesh.enabled is True
    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0)
    assert bundle is not None and _state(bundle) is BundleState.IN_TRANSIT
    mesh.step(1.0, now_s=1.0)
    assert _state(bundle) is BundleState.DELIVERED
    assert bundle.hops == 1
    assert mesh.delivered_total == 1


def test_multi_hop_takes_one_hop_per_tick() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [
                {"a": "dtn://dev/", "b": "dtn://relay/"},
                {"a": "dtn://relay/", "b": "dtn://ground/"},
            ],
        }
    )
    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0)
    assert bundle is not None

    mesh.step(1.0, now_s=1.0)
    assert _state(bundle) is BundleState.IN_TRANSIT
    assert bundle.holder_eid == "dtn://relay/"
    assert bundle.hops == 1

    mesh.step(1.0, now_s=2.0)
    assert _state(bundle) is BundleState.DELIVERED
    assert bundle.hops == 2


def test_store_and_forward_holds_until_contact_recovers() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [{"a": "dtn://dev/", "b": "dtn://ground/", "up": False}],
        }
    )
    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0)
    assert bundle is not None

    mesh.step(1.0, now_s=1.0)
    assert _state(bundle) is BundleState.IN_TRANSIT
    assert bundle.holder_eid == "dtn://dev/"

    assert mesh.set_contact("dtn://dev/", "dtn://ground/", up=True) is True
    mesh.step(1.0, now_s=2.0)
    assert _state(bundle) is BundleState.DELIVERED


def test_routing_prefers_the_shortest_up_path() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [
                {"a": "dtn://dev/", "b": "dtn://ground/"},
                {"a": "dtn://dev/", "b": "dtn://relay/"},
                {"a": "dtn://relay/", "b": "dtn://ground/"},
            ],
        }
    )
    hop = mesh.next_hop("dtn://dev/", "dtn://ground/")
    assert hop is not None and hop[0] == "dtn://ground/"

    # Drop the direct contact: the route now goes through the relay.
    mesh.set_contact("dtn://dev/", "dtn://ground/", up=False)
    hop = mesh.next_hop("dtn://dev/", "dtn://ground/")
    assert hop is not None and hop[0] == "dtn://relay/"


def test_custody_is_retained_on_loss_while_best_effort_is_dropped() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [
                {"a": "dtn://dev/", "b": "dtn://ground/", "loss_pct": 100.0}
            ],
            "custody_retries": 3,
        },
        rng=np.random.default_rng(0),
    )
    custodial = mesh.originate("dtn://ground/", 100, now_s=0.0, custody=True)
    best_effort = mesh.originate("dtn://ground/", 100, now_s=0.0, custody=False)
    assert custodial is not None and best_effort is not None

    mesh.step(1.0, now_s=1.0)
    assert custodial.state is BundleState.IN_TRANSIT
    assert custodial.attempts == 1
    assert mesh.retransmits_total == 1
    assert best_effort.state is BundleState.DROPPED
    assert mesh.dropped_total == 1


def test_custody_drops_after_exhausting_retries() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [
                {"a": "dtn://dev/", "b": "dtn://ground/", "loss_pct": 100.0}
            ],
            "custody_retries": 2,
        },
        rng=np.random.default_rng(0),
    )
    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0, custody=True)
    assert bundle is not None
    for tick in range(1, 5):
        mesh.step(1.0, now_s=float(tick))

    assert _state(bundle) is BundleState.DROPPED
    assert mesh.retransmits_total == 2
    assert mesh.dropped_total == 1


def test_expiry_drops_a_stale_bundle() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [{"a": "dtn://dev/", "b": "dtn://ground/", "up": False}],
        }
    )
    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0, lifetime_s=10.0)
    assert bundle is not None

    mesh.step(1.0, now_s=5.0)
    assert _state(bundle) is BundleState.IN_TRANSIT
    mesh.step(1.0, now_s=11.0)
    assert _state(bundle) is BundleState.EXPIRED
    assert mesh.expired_total == 1


def test_status_reports_topology_and_counters() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "nodes": ["dtn://ground/"],
            "contacts": [{"a": "dtn://dev/", "b": "dtn://ground/"}],
        }
    )
    mesh.originate("dtn://ground/", 100, now_s=0.0)
    status = mesh.status()
    assert status["enabled"] is True
    assert status["self_eid"] == "dtn://dev/"
    assert {n["eid"] for n in status["nodes"]} == {"dtn://dev/", "dtn://ground/"}
    assert status["in_transit"] == 1
    assert status["counters"]["originated"] == 1


def test_step_is_deterministic_under_a_seed() -> None:
    def run() -> tuple[int, int]:
        mesh = _mesh(
            {
                "self_eid": "dtn://dev/",
                "contacts": [
                    {"a": "dtn://dev/", "b": "dtn://ground/", "loss_pct": 40.0}
                ],
                "custody_retries": 50,
            },
            rng=np.random.default_rng(7),
        )
        mesh.originate("dtn://ground/", 100, now_s=0.0, custody=True)
        for tick in range(1, 20):
            mesh.step(1.0, now_s=float(tick))
        return (mesh.delivered_total, mesh.retransmits_total)

    assert run() == run()


def test_cgr_holds_for_a_scheduled_contact_then_delivers() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [
                {"a": "dtn://dev/", "b": "dtn://relay/"},
                {
                    "a": "dtn://relay/",
                    "b": "dtn://ground/",
                    "start_s": 10.0,
                    "end_s": 30.0,
                },
            ],
        }
    )
    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0, lifetime_s=100.0)
    assert bundle is not None

    # The dev->relay contact is up now: the bundle advances toward the relay.
    mesh.step(1.0, now_s=1.0)
    assert bundle.holder_eid == "dtn://relay/"
    assert bundle.hops == 1

    # The relay->ground contact is scheduled for t=10: the relay holds the bundle.
    mesh.step(1.0, now_s=2.0)
    assert bundle.holder_eid == "dtn://relay/"
    assert _state(bundle) is BundleState.IN_TRANSIT

    # The window opens: the bundle is delivered.
    mesh.step(1.0, now_s=10.0)
    assert _state(bundle) is BundleState.DELIVERED
    assert bundle.hops == 2


def test_cgr_holds_when_no_route_meets_the_deadline() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [
                {"a": "dtn://dev/", "b": "dtn://relay/"},
                {"a": "dtn://relay/", "b": "dtn://ground/", "start_s": 100.0},
            ],
        }
    )
    # The only route to ground opens at t=100, past the bundle's lifetime, so the
    # device never forwards it and the bundle expires in place.
    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0, lifetime_s=20.0)
    assert bundle is not None

    mesh.step(1.0, now_s=10.0)
    assert bundle.holder_eid == "dtn://dev/"
    assert _state(bundle) is BundleState.IN_TRANSIT

    mesh.step(1.0, now_s=21.0)
    assert _state(bundle) is BundleState.EXPIRED
    assert mesh.expired_total == 1
    assert mesh.delivered_total == 0


def test_lost_custody_ack_delivers_once_and_dedups_the_duplicate() -> None:
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [{"a": "dtn://dev/", "b": "dtn://ground/"}],
            "ack_loss_pct": 100.0,
            "custody_retries": 1,
        },
        rng=np.random.default_rng(0),
    )
    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0, custody=True)
    assert bundle is not None

    # Forward succeeds but the custody ack is lost: a copy is delivered while the
    # device retains the original to retransmit.
    mesh.step(1.0, now_s=1.0)
    assert mesh.delivered_total == 1
    assert mesh.retransmits_total == 1
    assert _state(bundle) is BundleState.IN_TRANSIT
    assert bundle.holder_eid == "dtn://dev/"

    # The retransmitted duplicate is deduplicated at the destination, not delivered
    # a second time.
    mesh.step(1.0, now_s=2.0)
    assert mesh.delivered_total == 1
    assert mesh.deduped_total == 1
    assert _state(bundle) is BundleState.DROPPED


def test_step_is_deterministic_with_ack_loss() -> None:
    def run() -> tuple[int, int, int]:
        mesh = _mesh(
            {
                "self_eid": "dtn://dev/",
                "contacts": [
                    {"a": "dtn://dev/", "b": "dtn://relay/"},
                    {"a": "dtn://relay/", "b": "dtn://ground/"},
                ],
                "ack_loss_pct": 50.0,
                "custody_retries": 10,
            },
            rng=np.random.default_rng(11),
        )
        mesh.originate("dtn://ground/", 100, now_s=0.0, custody=True)
        for tick in range(1, 30):
            mesh.step(1.0, now_s=float(tick))
        return (mesh.delivered_total, mesh.deduped_total, mesh.retransmits_total)

    assert run() == run()


def test_routing_breaks_arrival_ties_by_hop_count() -> None:
    # Two routes to ground arrive at t=10: a 2-hop route via 'a' and a 3-hop route
    # via 'b'/'c'. The 3-hop route's relays reach their hops earlier, so an
    # arrival-only relaxation would lock it in; the hop-count tie-break must still
    # prefer the 2-hop route.
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [
                {"a": "dtn://dev/", "b": "dtn://a/", "start_s": 9.0},
                {"a": "dtn://a/", "b": "dtn://ground/", "start_s": 10.0},
                {"a": "dtn://dev/", "b": "dtn://b/", "start_s": 0.0},
                {"a": "dtn://b/", "b": "dtn://c/", "start_s": 0.0},
                {"a": "dtn://c/", "b": "dtn://ground/", "start_s": 10.0},
            ],
        }
    )
    hop = mesh.next_hop("dtn://dev/", "dtn://ground/", now_s=0.0, size_bytes=0)
    assert hop is not None and hop[0] == "dtn://a/"


def test_zero_rate_contact_is_not_selected_for_routing() -> None:
    # The direct contact has zero capacity (rate_bps=0): routing must skip it and
    # deliver via the positive-rate relay instead of stalling on the dead link.
    mesh = _mesh(
        {
            "self_eid": "dtn://dev/",
            "contacts": [
                {"a": "dtn://dev/", "b": "dtn://ground/", "rate_bps": 0.0},
                {"a": "dtn://dev/", "b": "dtn://relay/"},
                {"a": "dtn://relay/", "b": "dtn://ground/"},
            ],
        }
    )
    hop = mesh.next_hop("dtn://dev/", "dtn://ground/", now_s=0.0, size_bytes=100)
    assert hop is not None and hop[0] == "dtn://relay/"

    bundle = mesh.originate("dtn://ground/", 100, now_s=0.0)
    assert bundle is not None
    mesh.step(1.0, now_s=1.0)
    assert bundle.holder_eid == "dtn://relay/"
    mesh.step(1.0, now_s=2.0)
    assert _state(bundle) is BundleState.DELIVERED


def test_recent_ids_evicts_oldest_beyond_maxlen() -> None:
    recent = _RecentIds(2)
    recent.add("a")
    recent.add("b")
    assert "a" in recent and "b" in recent
    recent.add("c")
    assert "a" not in recent
    assert "b" in recent and "c" in recent
