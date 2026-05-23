"""Storage Kalman filter: per-channel update, variance shrink, timestamp sync."""

from __future__ import annotations

import pytest

from nous.estimators.storage import StorageKalman
from nous.types import Observation


def test_starts_at_seeded_values() -> None:
    k = StorageKalman(initial_used_gib=120.0, initial_wear_pct=5.0)
    state = k.state()
    assert state.point["used_gib"] == pytest.approx(120.0)
    assert state.point["wear_pct"] == pytest.approx(5.0)


def test_predict_inflates_variance() -> None:
    k = StorageKalman()
    v0 = k.state().covariance["used_gib"]
    k.predict(300.0)
    assert k.state().covariance["used_gib"] > v0


def test_update_pulls_belief_toward_observation() -> None:
    k = StorageKalman(initial_used_gib=10.0, initial_wear_pct=1.0)
    obs = Observation(
        source="storage",
        ts_s=1.0,
        payload={"used_gib": 80.0, "wear_pct": 12.0},
        noise={"used_gib_sigma": 0.05, "wear_pct_sigma": 0.1},
    )
    k.update(obs)
    state = k.state()
    assert 10.0 < state.point["used_gib"] < 80.0
    assert 1.0 < state.point["wear_pct"] < 12.0


def test_update_shrinks_variance_below_initial() -> None:
    k = StorageKalman()
    v_initial = k.state().covariance["wear_pct"]
    obs = Observation(
        source="storage",
        ts_s=1.0,
        payload={"wear_pct": 5.0},
        noise={"wear_pct_sigma": 0.1},
    )
    k.update(obs)
    assert k.state().covariance["wear_pct"] < v_initial


def test_update_resynchronises_timestamp_to_observation() -> None:
    k = StorageKalman()
    obs = Observation(
        source="storage",
        ts_s=42.0,
        payload={"used_gib": 50.0},
        noise={"used_gib_sigma": 0.05},
    )
    k.update(obs)
    assert k.state().ts_s == pytest.approx(42.0)


def test_update_ignores_non_finite_timestamp() -> None:
    k = StorageKalman()
    k.predict(5.0)
    t_before = k.state().ts_s
    obs = Observation(
        source="storage",
        ts_s=float("inf"),
        payload={"used_gib": 30.0},
        noise={"used_gib_sigma": 0.05},
    )
    k.update(obs)
    assert k.state().ts_s == pytest.approx(t_before)
