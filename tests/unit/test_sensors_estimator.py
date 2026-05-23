"""Environmental Kalman: per-channel update, validation, timestamp sync."""

from __future__ import annotations

import pytest

from nous.estimators.sensors import EnvironmentalKalman
from nous.types import Observation


def test_starts_at_room_conditions() -> None:
    k = EnvironmentalKalman()
    state = k.state()
    assert state.point["temp_c"] == pytest.approx(22.0)
    assert state.point["humidity_pct"] == pytest.approx(50.0)
    assert state.point["baro_kpa"] == pytest.approx(101.3)


def test_predict_inflates_variance() -> None:
    k = EnvironmentalKalman()
    v0 = k.state().covariance["temp_c"]
    k.predict(60.0)
    assert k.state().covariance["temp_c"] > v0


def test_update_pulls_belief_toward_observation() -> None:
    k = EnvironmentalKalman()
    obs = Observation(
        source="sensors",
        ts_s=1.0,
        payload={"temp_c": 35.0, "humidity_pct": 80.0, "baro_kpa": 95.0},
        noise={
            "temp_c_sigma": 0.2,
            "humidity_pct_sigma": 1.0,
            "baro_kpa_sigma": 0.1,
        },
    )
    k.update(obs)
    state = k.state()
    assert 22.0 < state.point["temp_c"] < 35.0
    assert 50.0 < state.point["humidity_pct"] < 80.0
    assert 95.0 < state.point["baro_kpa"] < 101.3


def test_update_shrinks_variance_below_initial() -> None:
    k = EnvironmentalKalman()
    v0 = k.state().covariance["temp_c"]
    obs = Observation(
        source="sensors",
        ts_s=1.0,
        payload={"temp_c": 22.0},
        noise={"temp_c_sigma": 0.2},
    )
    k.update(obs)
    assert k.state().covariance["temp_c"] < v0


def test_out_of_range_observation_rejected() -> None:
    k = EnvironmentalKalman()
    before = k.state().point["temp_c"]
    k.update(
        Observation(
            source="sensors",
            ts_s=1.0,
            payload={"temp_c": 250.0},  # outside [-90, 90]
            noise={"temp_c_sigma": 0.2},
        )
    )
    assert k.state().point["temp_c"] == pytest.approx(before)
    assert k.rejected_updates == 1


def test_non_finite_observation_rejected() -> None:
    k = EnvironmentalKalman()
    k.update(
        Observation(
            source="sensors",
            ts_s=1.0,
            payload={"humidity_pct": float("nan")},
            noise={"humidity_pct_sigma": 1.0},
        )
    )
    assert k.rejected_updates == 1


def test_update_synchronises_timestamp() -> None:
    k = EnvironmentalKalman()
    k.update(
        Observation(
            source="sensors",
            ts_s=42.0,
            payload={"temp_c": 22.5},
            noise={"temp_c_sigma": 0.2},
        )
    )
    assert k.state().ts_s == pytest.approx(42.0)


def test_update_ignores_non_finite_timestamp() -> None:
    k = EnvironmentalKalman()
    k.predict(5.0)
    before = k.state().ts_s
    k.update(
        Observation(
            source="sensors",
            ts_s=float("inf"),
            payload={"temp_c": 22.5},
            noise={"temp_c_sigma": 0.2},
        )
    )
    assert k.state().ts_s == pytest.approx(before)
