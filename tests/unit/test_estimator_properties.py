"""Property-based tests for Kalman and EKF estimators.

The properties below are the contract the self-model relies on:

* ``predict(dt)`` never shrinks any covariance entry.
* ``update(obs)`` never grows any covariance entry past its pre-update value.
* The covariance is always non-negative.
* The point estimate stays inside the convex hull of the prior and the
  observation (1-D Kalman gain has range [0, 1]).
* NaN / Inf / out-of-range inputs do not poison the estimate -- the
  filter either rejects the update or clamps to the validation envelope.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from nous.estimators.apu import ApuEstimator
from nous.estimators.biometrics import BiometricsKalman
from nous.estimators.position import PositionEKF
from nous.estimators.power import PowerEstimator
from nous.types import Observation

_finite_floats = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
)


def _power_obs(soc: float, voltage: float = 13.0, current: float = 1.0) -> Observation:
    return Observation(
        source="power",
        ts_s=0.0,
        payload={"soc_pct": soc, "voltage_v": voltage, "current_a": current},
        noise={"soc_pct_sigma": 0.5, "voltage_v_sigma": 0.05, "current_a_sigma": 0.1},
    )


@given(dt=st.floats(min_value=1e-3, max_value=3600.0))
def test_power_predict_does_not_shrink_covariance(dt: float) -> None:
    est = PowerEstimator()
    before = est.state().covariance["soc_pct"]
    est.predict(dt)
    after = est.state().covariance["soc_pct"]
    assert after >= before


@given(soc=st.floats(min_value=0.0, max_value=100.0))
def test_power_update_keeps_estimate_in_convex_hull(soc: float) -> None:
    est = PowerEstimator(initial_soc=50.0, soc_sigma=5.0)
    est.predict(1.0)
    est.update(_power_obs(soc=soc))
    new = est.state().point["soc_pct"]
    lo = min(50.0, soc)
    hi = max(50.0, soc)
    assert lo - 1e-9 <= new <= hi + 1e-9


@given(soc=st.floats(min_value=0.0, max_value=100.0))
def test_power_update_does_not_grow_covariance(soc: float) -> None:
    est = PowerEstimator(initial_soc=50.0, soc_sigma=5.0)
    before = est.state().covariance["soc_pct"]
    est.update(_power_obs(soc=soc))
    after = est.state().covariance["soc_pct"]
    assert after <= before + 1e-12


@given(garbage=st.sampled_from([math.nan, math.inf, -math.inf, -1.0, 101.0]))
def test_power_rejects_out_of_range_soc(garbage: float) -> None:
    est = PowerEstimator(initial_soc=42.0)
    est.update(_power_obs(soc=garbage))
    point = est.state().point["soc_pct"]
    assert math.isfinite(point)
    assert 0.0 <= point <= 100.0


@given(
    lat=_finite_floats.filter(lambda v: -89.0 <= v <= 89.0),
    lon=_finite_floats.filter(lambda v: -179.0 <= v <= 179.0),
)
def test_position_accepts_valid_lat_lon(lat: float, lon: float) -> None:
    est = PositionEKF()
    obs = Observation(
        source="position",
        ts_s=1.0,
        payload={"lat": lat, "lon": lon, "alt_m": 100.0},
        noise={"lat_sigma": 1e-5, "lon_sigma": 1e-5, "alt_m_sigma": 1.0},
    )
    est.predict(1.0)
    est.update(obs)
    state = est.state()
    assert state.point["lat"] == pytest.approx(lat, rel=1e-3, abs=1e-3)
    assert state.point["lon"] == pytest.approx(lon, rel=1e-3, abs=1e-3)
    assert est.rejected_updates == 0


def test_position_wraps_lon_innovation_across_antimeridian() -> None:
    """An EKF prior at 179.9 must blend toward an obs at -179.9 via the short arc."""
    est = PositionEKF()
    est.update(
        Observation(
            source="position",
            ts_s=1.0,
            payload={"lat": 0.0, "lon": 179.9, "alt_m": 0.0},
            noise={"lat_sigma": 1e-5, "lon_sigma": 1e-5, "alt_m_sigma": 1.0},
        )
    )
    est.predict(1.0)
    est.update(
        Observation(
            source="position",
            ts_s=2.0,
            payload={"lat": 0.0, "lon": -179.9, "alt_m": 0.0},
            noise={"lat_sigma": 1e-5, "lon_sigma": 1e-5, "alt_m_sigma": 1.0},
        )
    )
    state = est.state()
    lon = state.point["lon"]
    assert -180.0 <= lon <= 180.0
    short_arc_distance = min(abs(lon - (-179.9)), 360.0 - abs(lon - (-179.9)))
    assert short_arc_distance < 1.0


@given(
    lat=st.sampled_from([math.nan, math.inf, -math.inf, 100.0, -200.0]),
)
def test_position_rejects_garbage_lat(lat: float) -> None:
    est = PositionEKF()
    obs = Observation(
        source="position",
        ts_s=1.0,
        payload={"lat": lat, "lon": 0.0, "alt_m": 0.0},
    )
    est.update(obs)
    assert est.rejected_updates == 1
    assert est.state().point["lat"] == 0.0


@given(hr=_finite_floats.filter(lambda v: 20.0 <= v <= 240.0))
def test_biometrics_in_envelope_accepted(hr: float) -> None:
    est = BiometricsKalman()
    obs = Observation(
        source="biometrics",
        ts_s=1.0,
        payload={"heart_rate_bpm": hr},
        noise={"heart_rate_bpm_sigma": 2.0},
    )
    est.update(obs)
    point = est.state().point["heart_rate_bpm"]
    # Convex hull: between prior (70 bpm) and observation, after Kalman gain.
    assert min(70.0, hr) - 1e-6 <= point <= max(70.0, hr) + 1e-6


@given(garbage=st.sampled_from([math.nan, math.inf, -math.inf, -10.0, 500.0]))
def test_biometrics_rejects_out_of_envelope(garbage: float) -> None:
    est = BiometricsKalman()
    obs = Observation(
        source="biometrics",
        ts_s=1.0,
        payload={"heart_rate_bpm": garbage},
    )
    est.update(obs)
    assert est.rejected_updates == 1
    assert est.state().point["heart_rate_bpm"] == 70.0


@given(
    soc=st.floats(min_value=0.0, max_value=100.0),
    dt=st.floats(min_value=0.01, max_value=10.0),
    n=st.integers(min_value=5, max_value=50),
)
@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_power_steady_state_covariance_bounded(soc: float, dt: float, n: int) -> None:
    est = PowerEstimator(initial_soc=soc, soc_sigma=10.0)
    for _ in range(n):
        est.predict(dt)
        est.update(_power_obs(soc=soc))
    cov = est.state().covariance["soc_pct"]
    # Covariance must remain non-negative and finite.
    assert math.isfinite(cov)
    assert cov >= 0.0


@given(
    solar=_finite_floats.filter(lambda v: 0.0 <= v <= 100.0),
    fuelcell=_finite_floats.filter(lambda v: 0.0 <= v <= 50.0),
)
def test_apu_covariance_never_negative(solar: float, fuelcell: float) -> None:
    est = ApuEstimator()
    obs = Observation(
        source="apu",
        ts_s=0.0,
        payload={"solar_w": solar, "fuelcell_w": fuelcell},
        noise={"solar_w_sigma": 1.0, "fuelcell_w_sigma": 1.0},
    )
    est.predict(0.5)
    est.update(obs)
    state = est.state()
    for key in ("solar_w", "fuelcell_w", "total_w"):
        assert state.covariance[key] >= 0.0


@given(
    n=st.integers(min_value=1, max_value=200),
    dt=st.floats(min_value=0.05, max_value=1.0),
)
def test_apu_predict_monotonically_grows_covariance(n: int, dt: float) -> None:
    est = ApuEstimator()
    last = est.state().covariance["total_w"]
    for _ in range(n):
        est.predict(dt)
        new = est.state().covariance["total_w"]
        assume(math.isfinite(new))
        assert new >= last - 1e-12
        last = new
