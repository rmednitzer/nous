"""APU estimator: per-source smoothing and covariance behaviour."""

from __future__ import annotations

import pytest

from nous.estimators.apu import ApuEstimator
from nous.types import Observation


def _obs(**values: float) -> Observation:
    payload = {
        "solar_w": values.get("solar_w", 0.0),
        "fuelcell_w": values.get("fuelcell_w", 0.0),
        "vehicle_w": values.get("vehicle_w", 0.0),
        "usbc_w": values.get("usbc_w", 0.0),
        "total_w": values.get("total_w", sum(values.values())),
    }
    noise = {
        "solar_w_sigma": 1.0,
        "fuelcell_w_sigma": 0.5,
        "vehicle_w_sigma": 0.5,
        "usbc_w_sigma": 0.2,
        "total_w_sigma": 2.0,
    }
    return Observation(source="apu", ts_s=0.0, payload=payload, noise=noise)


def test_starts_at_zero_each_source() -> None:
    est = ApuEstimator()
    state = est.state()
    for key in ("solar_w", "fuelcell_w", "vehicle_w", "usbc_w", "total_w"):
        assert state.point[key] == 0.0


def test_predict_grows_each_channel_variance() -> None:
    est = ApuEstimator()
    before = est.state().covariance["solar_w"]
    est.predict(5.0)
    assert est.state().covariance["solar_w"] > before


def test_update_pulls_toward_observation() -> None:
    est = ApuEstimator()
    est.predict(1.0)
    est.update(_obs(solar_w=30.0))
    state = est.state()
    assert 0.0 < state.point["solar_w"] <= 30.0


def test_update_converges_under_steady_signal() -> None:
    est = ApuEstimator()
    for _ in range(100):
        est.predict(0.5)
        est.update(_obs(solar_w=20.0, fuelcell_w=10.0, total_w=30.0))
    state = est.state()
    assert state.point["solar_w"] == pytest.approx(20.0, abs=1.0)
    assert state.point["fuelcell_w"] == pytest.approx(10.0, abs=1.0)
    assert state.point["total_w"] == pytest.approx(30.0, abs=2.0)


def test_channels_are_independent() -> None:
    est = ApuEstimator()
    for _ in range(50):
        est.predict(0.5)
        est.update(_obs(solar_w=15.0))
    state = est.state()
    assert state.point["solar_w"] > 5.0
    assert state.point["fuelcell_w"] == pytest.approx(0.0, abs=0.5)
