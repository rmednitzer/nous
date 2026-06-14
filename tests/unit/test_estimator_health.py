"""Innovation gating, variance floors, reset recovery, and the health surface.

These cover the behaviour ADR 0045 adds on top of the scalar Kalman
estimators: a converged filter rejects an outlier, seeds itself from its first
measurement, never reports a falsely certain zero variance, adopts a sustained
shift through a counted reset, and surfaces all of that in an
:class:`~nous.types.EstimatorHealth` block.
"""

from __future__ import annotations

import pytest

from nous.estimators.apu import ApuEstimator
from nous.estimators.base import Estimator
from nous.estimators.biometrics import BiometricsKalman
from nous.estimators.comms import CommsParticleFilter
from nous.estimators.compute import ComputeKalman
from nous.estimators.health import ChannelSpec, ScalarChannel, build_health
from nous.estimators.position import PositionKalman
from nous.estimators.power import PowerEstimator
from nous.estimators.sensors import EnvironmentalKalman
from nous.estimators.storage import StorageKalman
from nous.estimators.thermal import ThermalKalman
from nous.types import EstimatorHealth, Observation


def _power_obs(soc: float) -> Observation:
    return Observation(
        source="power",
        ts_s=0.0,
        payload={"soc_pct": soc},
        noise={"soc_pct_sigma": 0.5},
    )


def _converged_power(initial: float = 50.0) -> PowerEstimator:
    est = PowerEstimator(initial_soc=initial, soc_sigma=5.0)
    for _ in range(40):
        est.predict(1.0)
        est.update(_power_obs(initial))
    return est


# --- ScalarChannel primitive -------------------------------------------------


def test_channel_seeds_first_fusion_through_the_gate() -> None:
    # A fresh channel must accept its first measurement however far it is:
    # an unconstrained filter has to initialise from its first reading.
    ch = ScalarChannel(0.0, 1.0, ChannelSpec(gate_sigma=5.0, reset_after=0))
    # The far value would fail the gate on a converged channel; on the first
    # fusion it is accepted (and Kalman-blended toward) rather than rejected.
    assert ch.fuse(1000.0, 0.01) is True
    assert ch.value > 900.0
    assert ch.rejected == 0


def test_channel_gates_outlier_once_converged() -> None:
    ch = ScalarChannel(0.0, 1.0, ChannelSpec(gate_sigma=5.0, reset_after=0))
    ch.fuse(0.0, 0.01)  # seed
    for _ in range(20):
        ch.fuse(0.0, 0.01)
    accepted = ch.fuse(100.0, 0.01)
    assert accepted is False
    assert ch.rejected == 1
    assert ch.test_ratio > 1.0
    assert ch.value == pytest.approx(0.0, abs=1e-3)


def test_channel_resets_onto_sustained_shift() -> None:
    ch = ScalarChannel(0.0, 1.0, ChannelSpec(gate_sigma=5.0, reset_after=3))
    ch.fuse(0.0, 0.01)
    for _ in range(10):
        ch.fuse(0.0, 0.01)
    results = [ch.fuse(100.0, 0.01) for _ in range(3)]
    assert results == [False, False, True]  # third one adopts via reset
    assert ch.resets == 1
    assert ch.value == pytest.approx(100.0, abs=1.0)


def test_channel_floor_blocks_collapse_to_zero() -> None:
    ch = ScalarChannel(0.0, 1.0, ChannelSpec(var_floor=1e-6))
    for _ in range(50):
        ch.fuse(0.0, 0.0)  # perfect observations would otherwise zero the variance
    assert ch.var >= 1e-6


def test_channel_filtered_ratio_carries_innovation_sign() -> None:
    high = ScalarChannel(0.0, 1.0, ChannelSpec(gate_sigma=5.0, reset_after=0))
    low = ScalarChannel(0.0, 1.0, ChannelSpec(gate_sigma=5.0, reset_after=0))
    for ch in (high, low):
        ch.fuse(0.0, 0.01)
        for _ in range(20):
            ch.fuse(0.0, 0.01)
    high.fuse(50.0, 0.01)  # positive innovation
    low.fuse(-50.0, 0.01)  # negative innovation
    assert high.test_ratio_filtered > 0.0
    assert low.test_ratio_filtered < 0.0


def test_build_health_aggregates_channels() -> None:
    a = ScalarChannel(0.0, 1.0)
    b = ScalarChannel(0.0, 1.0)
    a.fuse(0.0, 0.01)
    health = build_health({"a": a, "b": b}, rejected_extra=2, dead_reckoning=True)
    assert isinstance(health, EstimatorHealth)
    assert health.rejected_updates == 2
    assert health.dead_reckoning is True
    assert set(health.test_ratio) == {"a", "b"}


# --- Estimator-level behaviour ----------------------------------------------


def test_power_rejects_implausible_soc_jump_once_converged() -> None:
    est = _converged_power(50.0)
    before = est.state()
    est.update(_power_obs(95.0))
    after = est.state()
    assert after.health is not None
    assert after.health.rejected_updates == 1
    assert after.health.test_ratio["soc_pct"] > 1.0
    assert after.point["soc_pct"] == pytest.approx(before.point["soc_pct"], abs=1.0)


def test_power_adopts_sustained_soc_shift_via_reset() -> None:
    est = _converged_power(50.0)
    for _ in range(3):
        est.update(_power_obs(95.0))
    state = est.state()
    assert state.health is not None
    assert state.health.reset_count == 1
    assert state.point["soc_pct"] > 90.0


def test_position_variance_never_collapses_to_zero() -> None:
    # The live defect: lat/lon variance read exactly 0.0, a false certainty.
    est = PositionKalman()
    obs = Observation(
        source="position",
        ts_s=1.0,
        payload={"lat": 47.0, "lon": 13.0, "alt_m": 500.0},
        noise={"lat_sigma": 1e-5, "lon_sigma": 1e-5, "alt_m_sigma": 1.0},
    )
    for tick in range(20):
        est.predict(1.0)
        obs = obs.model_copy(update={"ts_s": float(tick + 2)})
        est.update(obs)
    cov = est.state().covariance
    assert cov["lat"] > 0.0
    assert cov["lon"] > 0.0
    assert cov["lat"] >= 1e-10


def test_position_dead_reckoning_flag_tracks_fix_availability() -> None:
    est = PositionKalman()
    fix = Observation(
        source="position",
        ts_s=1.0,
        payload={"lat": 47.0, "lon": 13.0, "alt_m": 500.0},
        noise={"lat_sigma": 1e-5, "lon_sigma": 1e-5, "alt_m_sigma": 1.0},
    )
    est.update(fix)
    fixed = est.state().health
    assert fixed is not None
    assert fixed.dead_reckoning is False

    est.predict(1.0)
    est.update(Observation(source="position", ts_s=2.0, payload={}, noise={}))
    health = est.state().health
    assert health is not None
    assert health.dead_reckoning is True
    assert health.fused is False


def test_every_estimator_reports_health() -> None:
    estimators: list[Estimator] = [
        PowerEstimator(),
        ApuEstimator(),
        ThermalKalman(),
        ComputeKalman(),
        StorageKalman(),
        CommsParticleFilter(),
        PositionKalman(),
        EnvironmentalKalman(),
        BiometricsKalman(),
    ]
    for est in estimators:
        health = est.state().health
        assert isinstance(health, EstimatorHealth), est.name
        assert health.healthy is True


def test_comms_reports_health_block() -> None:
    f = CommsParticleFilter(particles=32, seed=3)
    f.update(
        Observation(
            source="comms",
            ts_s=1.0,
            payload={
                "links": [
                    {
                        "link_id": "lte",
                        "rssi_dbm": -70.0,
                        "loss_pct": 1.0,
                        "throughput_bps": 1_000_000.0,
                        "connected": True,
                    }
                ]
            },
            noise={},
        )
    )
    health = f.state().health
    assert health is not None
    assert health.healthy is True
    assert health.fused is True
    assert health.reset_count == 0
