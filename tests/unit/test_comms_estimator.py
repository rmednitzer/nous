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
