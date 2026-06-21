"""Power SoC estimator: tracking and covariance bound."""

from __future__ import annotations

import pytest

from nous.estimators.power import PowerEstimator
from nous.types import Observation


def _obs(
    soc: float, voltage: float = 13.0, current: float = 2.0, load: float = 10.0
) -> Observation:
    return Observation(
        source="power",
        ts_s=0.0,
        payload={
            "soc_pct": soc,
            "voltage_v": voltage,
            "current_a": current,
            "load_w": load,
        },
        noise={
            "soc_pct_sigma": 0.5,
            "voltage_v_sigma": 0.05,
            "current_a_sigma": 0.10,
            "load_w_sigma": 0.25,
        },
    )


def test_starts_at_initial_soc() -> None:
    est = PowerEstimator(initial_soc=80.0)
    state = est.state()
    assert state.point["soc_pct"] == pytest.approx(80.0)


def test_predict_grows_variance() -> None:
    est = PowerEstimator(soc_sigma=1.0)
    before = est.state().covariance["soc_pct"]
    est.predict(10.0)
    after = est.state().covariance["soc_pct"]
    assert after > before


def test_update_shrinks_variance() -> None:
    est = PowerEstimator(soc_sigma=5.0)
    before = est.state().covariance["soc_pct"]
    est.predict(1.0)
    est.update(_obs(soc=90.0))
    after = est.state().covariance["soc_pct"]
    assert after < before


def test_update_pulls_estimate_toward_observation() -> None:
    est = PowerEstimator(initial_soc=100.0, soc_sigma=5.0)
    est.predict(1.0)
    est.update(_obs(soc=80.0))
    state = est.state()
    assert 80.0 < state.point["soc_pct"] < 100.0


def test_covariance_bound_at_steady_state_above_20pct() -> None:
    est = PowerEstimator(initial_soc=50.0, soc_sigma=10.0)
    for _ in range(200):
        est.predict(0.5)
        est.update(_obs(soc=50.0))
    sigma = est.state().covariance["soc_pct"] ** 0.5
    assert sigma <= 2.0, f"SoC sigma {sigma:.3f} exceeds 2pp bound (model card)"


def test_current_passed_through() -> None:
    est = PowerEstimator()
    est.update(_obs(soc=50.0, current=3.5))
    assert est.state().point["current_a"] == pytest.approx(3.5)


def test_load_w_in_state() -> None:
    est = PowerEstimator(initial_load_w=12.0)
    state = est.state()
    assert state.point["load_w"] == pytest.approx(12.0)
    assert "load_w" in state.covariance


def test_load_predict_grows_variance() -> None:
    est = PowerEstimator(load_sigma=1.0)
    before = est.state().covariance["load_w"]
    est.predict(10.0)
    assert est.state().covariance["load_w"] > before


def test_load_update_tracks_observation_and_shrinks_variance() -> None:
    est = PowerEstimator(initial_load_w=0.0, load_sigma=5.0)
    before = est.state().covariance["load_w"]
    est.predict(1.0)
    est.update(_obs(soc=50.0, load=40.0))
    state = est.state()
    assert 0.0 < state.point["load_w"] < 40.0  # pulled toward the observation
    assert state.covariance["load_w"] < before
