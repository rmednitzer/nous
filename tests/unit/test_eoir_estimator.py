"""Unit tests for the BL-055 EO/IR detection-range Kalman filter."""

from __future__ import annotations

import math

import pytest

from nous.estimators.eoir import EoirKalman
from nous.types import Observation


def _obs(eo: float, ir: float, ts: float = 0.0) -> Observation:
    return Observation(
        source="eoir",
        ts_s=ts,
        payload={"eo_range_m": eo, "ir_range_m": ir},
        noise={"eo_range_m_sigma": 200.0, "ir_range_m_sigma": 150.0},
    )


def test_starts_at_clear_air_defaults() -> None:
    k = EoirKalman()
    s = k.state()
    assert s.point["eo_range_m"] == pytest.approx(12000.0)
    assert s.point["ir_range_m"] == pytest.approx(8000.0)


def test_predict_inflates_variance() -> None:
    k = EoirKalman()
    before = k.state().covariance["eo_range_m"]
    k.predict(1.0)
    assert k.state().covariance["eo_range_m"] > before


def test_update_pulls_belief_toward_observation() -> None:
    k = EoirKalman()
    k.update(_obs(10000.0, 7000.0))
    eo = k.state().point["eo_range_m"]
    # Moves toward the reading without reaching it in one step.
    assert 10000.0 < eo < 12000.0


def test_update_shrinks_variance_below_initial() -> None:
    k = EoirKalman()
    before = k.state().covariance["eo_range_m"]
    k.update(_obs(11000.0, 7500.0))
    assert k.state().covariance["eo_range_m"] < before


def test_out_of_range_observation_rejected() -> None:
    k = EoirKalman()
    k.update(_obs(1.0e9, 7000.0))  # eo beyond the 60 km bound
    assert k.state().point["eo_range_m"] == pytest.approx(12000.0)
    assert k.rejected_updates == 1


def test_non_finite_observation_rejected() -> None:
    k = EoirKalman()
    k.update(_obs(math.nan, 7000.0))
    assert k.state().point["eo_range_m"] == pytest.approx(12000.0)
    assert k.rejected_updates == 1


def test_update_synchronises_timestamp() -> None:
    k = EoirKalman()
    k.update(_obs(11000.0, 7500.0, ts=42.0))
    assert k.state().ts_s == pytest.approx(42.0)


def test_update_ignores_non_finite_timestamp() -> None:
    k = EoirKalman()
    k.predict(3.0)
    k.update(_obs(11000.0, 7500.0, ts=math.inf))
    assert k.state().ts_s == pytest.approx(3.0)
