"""Thermal Kalman filter: junction + enclosure two-state belief."""

from __future__ import annotations

import pytest

from nous.estimators.thermal import ThermalKalman
from nous.types import Observation


def test_starts_at_seeded_values() -> None:
    k = ThermalKalman(initial_junction_c=30.0, initial_enclosure_c=27.0)
    state = k.state()
    assert state.point["junction_c"] == pytest.approx(30.0)
    assert state.point["enclosure_c"] == pytest.approx(27.0)
    assert state.covariance["junction_c"] > 0.0
    assert state.covariance["enclosure_c"] > 0.0


def test_predict_inflates_variance() -> None:
    k = ThermalKalman()
    v0 = k.state().covariance["junction_c"]
    k.predict(5.0)
    v1 = k.state().covariance["junction_c"]
    assert v1 > v0


def test_update_pulls_belief_toward_observation() -> None:
    k = ThermalKalman(initial_junction_c=40.0, initial_enclosure_c=35.0)
    obs = Observation(
        source="thermal",
        ts_s=1.0,
        payload={"junction_c": 70.0, "enclosure_c": 45.0},
        noise={"junction_c_sigma": 1.0, "enclosure_c_sigma": 0.5},
    )
    k.update(obs)
    state = k.state()
    assert state.point["junction_c"] > 40.0
    assert state.point["junction_c"] < 70.0
    assert state.point["enclosure_c"] > 35.0
    assert state.point["enclosure_c"] < 45.0


def test_update_shrinks_variance_below_initial() -> None:
    k = ThermalKalman()
    v_initial = k.state().covariance["junction_c"]
    obs = Observation(
        source="thermal",
        ts_s=1.0,
        payload={"junction_c": 50.0},
        noise={"junction_c_sigma": 0.5},
    )
    k.update(obs)
    assert k.state().covariance["junction_c"] < v_initial


def test_update_resynchronises_timestamp_to_observation() -> None:
    k = ThermalKalman()
    obs = Observation(
        source="thermal",
        ts_s=42.5,
        payload={"junction_c": 30.0},
        noise={"junction_c_sigma": 1.0},
    )
    k.update(obs)
    assert k.state().ts_s == pytest.approx(42.5)


def test_update_ignores_non_finite_timestamp() -> None:
    k = ThermalKalman()
    k.predict(2.0)
    t_before = k.state().ts_s
    obs = Observation(
        source="thermal",
        ts_s=float("nan"),
        payload={"junction_c": 30.0},
        noise={"junction_c_sigma": 1.0},
    )
    k.update(obs)
    assert k.state().ts_s == pytest.approx(t_before)
