"""Compute Kalman filter: per-channel update, variance shrink, timestamp sync."""

from __future__ import annotations

import pytest

from nous.estimators.compute import ComputeKalman
from nous.types import Observation


def test_starts_at_seeded_values() -> None:
    k = ComputeKalman(initial_load_pct=20.0, initial_draw_w=15.0)
    state = k.state()
    assert state.point["load_pct"] == pytest.approx(20.0)
    assert state.point["draw_w"] == pytest.approx(15.0)


def test_predict_inflates_variance() -> None:
    k = ComputeKalman()
    v0 = k.state().covariance["draw_w"]
    k.predict(5.0)
    assert k.state().covariance["draw_w"] > v0


def test_update_pulls_belief_toward_observation() -> None:
    k = ComputeKalman(initial_load_pct=20.0, initial_draw_w=15.0)
    obs = Observation(
        source="compute",
        ts_s=1.0,
        payload={"load_pct": 60.0, "draw_w": 35.0},
        noise={"load_pct_sigma": 1.5, "draw_w_sigma": 0.5},
    )
    k.update(obs)
    state = k.state()
    assert 20.0 < state.point["load_pct"] < 60.0
    assert 15.0 < state.point["draw_w"] < 35.0


def test_update_shrinks_variance_below_initial() -> None:
    k = ComputeKalman()
    v_initial = k.state().covariance["draw_w"]
    obs = Observation(
        source="compute",
        ts_s=1.0,
        payload={"draw_w": 25.0},
        noise={"draw_w_sigma": 0.5},
    )
    k.update(obs)
    assert k.state().covariance["draw_w"] < v_initial


def test_update_resynchronises_timestamp_to_observation() -> None:
    k = ComputeKalman()
    obs = Observation(
        source="compute",
        ts_s=12.5,
        payload={"load_pct": 30.0},
        noise={"load_pct_sigma": 1.0},
    )
    k.update(obs)
    assert k.state().ts_s == pytest.approx(12.5)


def test_update_ignores_non_finite_timestamp() -> None:
    k = ComputeKalman()
    k.predict(2.0)
    t_before = k.state().ts_s
    obs = Observation(
        source="compute",
        ts_s=float("nan"),
        payload={"load_pct": 30.0},
        noise={"load_pct_sigma": 1.0},
    )
    k.update(obs)
    assert k.state().ts_s == pytest.approx(t_before)
