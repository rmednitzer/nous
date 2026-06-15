"""Multi-node DTN mesh: routing, store-and-forward, custody (BL-056 / ADR 0062)."""

from __future__ import annotations

from typing import Any

import numpy as np

from nous.state.dtn_mesh import BundleState, DtnMesh, MeshBundle


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
