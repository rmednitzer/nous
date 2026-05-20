"""Power SoC estimator: tracking and covariance bound."""

from __future__ import annotations

import pytest

from nous.estimators.power import PowerEstimator
from nous.types import Observation


def _obs(soc: float, voltage: float = 13.0, current: float = 2.0) -> Observation:
    return Observation(
        source="power",
        ts_s=0.0,
        payload={"soc_pct": soc, "voltage_v": voltage, "current_a": current},
        noise={
            "soc_pct_sigma": 0.5,
            "voltage_v_sigma": 0.05,
            "current_a_sigma": 0.10,
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
