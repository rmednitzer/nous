"""Comms estimator: per-link belief, connected count, timestamp sync."""

from __future__ import annotations

import pytest

from nous.estimators.comms import CommsParticleFilter
from nous.types import Observation


def _obs(*links: dict[str, float | bool | str], ts: float = 1.0) -> Observation:
    return Observation(
        source="comms",
        ts_s=ts,
        payload={"links": list(links)},
        noise={},
    )


def test_starts_with_no_links() -> None:
    f = CommsParticleFilter()
    state = f.state()
    assert state.point["connected_links"] == pytest.approx(0.0)
    assert state.point["total_links"] == pytest.approx(0.0)


def test_update_tracks_per_link_state() -> None:
    f = CommsParticleFilter()
    f.update(
        _obs(
            {
                "link_id": "lte",
                "rssi_dbm": -70.0,
                "loss_pct": 1.0,
                "throughput_bps": 1_000_000.0,
                "connected": True,
            }
        )
    )
    links = f.links()
    assert len(links) == 1
    assert links[0].link_id == "lte"
    assert links[0].connected is True


def test_disconnected_links_counted_in_total_not_connected() -> None:
    f = CommsParticleFilter()
    f.update(
        _obs(
            {
                "link_id": "lte",
                "rssi_dbm": -70.0,
                "loss_pct": 0.5,
                "throughput_bps": 1_000_000.0,
                "connected": True,
            },
            {
                "link_id": "lora",
                "rssi_dbm": -120.0,
                "loss_pct": 99.0,
                "throughput_bps": 0.0,
                "connected": False,
            },
        )
    )
    state = f.state()
    assert state.point["connected_links"] == pytest.approx(1.0)
    assert state.point["total_links"] == pytest.approx(2.0)


def test_zero_throughput_means_not_connected_even_if_flag_set() -> None:
    f = CommsParticleFilter()
    f.update(
        _obs(
            {
                "link_id": "lte",
                "rssi_dbm": -70.0,
                "loss_pct": 1.0,
                "throughput_bps": 0.0,
                "connected": True,
            }
        )
    )
    state = f.state()
    assert state.point["connected_links"] == pytest.approx(0.0)


def test_update_synchronises_timestamp() -> None:
    f = CommsParticleFilter()
    f.update(_obs(ts=15.0))
    assert f.state().ts_s == pytest.approx(15.0)


def test_update_ignores_non_finite_timestamp() -> None:
    f = CommsParticleFilter()
    f.predict(3.0)
    before = f.state().ts_s
    f.update(
        Observation(source="comms", ts_s=float("nan"), payload={"links": []}, noise={})
    )
    assert f.state().ts_s == pytest.approx(before)


def test_malformed_link_entries_skipped() -> None:
    f = CommsParticleFilter()
    f.update(
        Observation(
            source="comms",
            ts_s=1.0,
            payload={"links": ["not a dict", {"missing_link_id": 1}]},
            noise={},
        )
    )
    assert f.links() == []


def test_loss_pct_clamped_to_zero_one_hundred() -> None:
    f = CommsParticleFilter()
    f.update(
        _obs(
            {
                "link_id": "lte",
                "rssi_dbm": -70.0,
                "loss_pct": 250.0,
                "throughput_bps": 1000.0,
                "connected": True,
            }
        )
    )
    assert f.links()[0].loss_pct == pytest.approx(100.0)


def test_belief_converges_to_connected_on_healthy_link() -> None:
    """A healthy link with good throughput should converge to belief ~ 1."""
    f = CommsParticleFilter(particles=64, seed=42)
    for tick in range(20):
        f.predict(1.0)
        f.update(
            _obs(
                {
                    "link_id": "lte",
                    "rssi_dbm": -65.0,
                    "loss_pct": 0.5,
                    "throughput_bps": 1_000_000.0,
                    "connected": True,
                },
                ts=float(tick + 1),
            )
        )
    belief = f.belief("lte")
    assert belief is not None
    assert belief > 0.85


def test_belief_converges_to_disconnected_on_silent_link() -> None:
    """A link with zero throughput should converge to belief ~ 0."""
    f = CommsParticleFilter(particles=64, seed=7)
    for tick in range(20):
        f.predict(1.0)
        f.update(
            _obs(
                {
                    "link_id": "lora",
                    "rssi_dbm": -115.0,
                    "loss_pct": 95.0,
                    "throughput_bps": 0.0,
                    "connected": False,
                },
                ts=float(tick + 1),
            )
        )
    belief = f.belief("lora")
    assert belief is not None
    assert belief < 0.15


def test_state_covariance_is_finite_and_non_negative() -> None:
    """Aggregate covariance must respect the engine's post-tick invariants."""
    f = CommsParticleFilter(particles=32, seed=3)
    f.update(
        _obs(
            {
                "link_id": "lte",
                "rssi_dbm": -80.0,
                "loss_pct": 5.0,
                "throughput_bps": 500_000.0,
                "connected": True,
            }
        )
    )
    state = f.state()
    cov = state.covariance["connected_links"]
    assert isinstance(cov, float)
    assert cov >= 0.0
    assert cov < 1.0


def test_deterministic_under_seed() -> None:
    """Two filters with the same seed produce identical particle trajectories."""
    obs = _obs(
        {
            "link_id": "lte",
            "rssi_dbm": -90.0,
            "loss_pct": 30.0,
            "throughput_bps": 50_000.0,
            "connected": True,
        }
    )
    a = CommsParticleFilter(particles=16, seed=11)
    b = CommsParticleFilter(particles=16, seed=11)
    for _ in range(5):
        a.predict(1.0)
        a.update(obs)
        b.predict(1.0)
        b.update(obs)
    assert a.belief("lte") == pytest.approx(b.belief("lte"))
