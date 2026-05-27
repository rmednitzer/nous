"""Property-based invariants for subsystem physics (ADR 0020).

The existing ``tests/unit/test_estimator_properties.py`` covers the
filter contract; this file covers the subsystem layer underneath.
The invariants are closed-form facts about the modelled physics,
not numeric examples: a regression that breaks the invariant fails
on every Hypothesis seed, not only on the seed that picked the
example.

PR #58 landed the first increment (compute draw monotonicity in
load, power SoC monotonicity under discharge, thermal
convergence to ambient at zero load, comms link-age
monotonicity, tx-resets-age). This file extends to the rest of
the ADR 0020 list: Peukert capacity-vs-current monotonicity,
thermal junction-above-enclosure under load, compute throttling
never-increases, position EKF covariance growth under predict-
only and shrink under update, storage used / wear monotonicity,
FSM transition closure. The comms SNR-to-throughput coupling
from the ADR text is not modelled in the current subsystem (RSSI,
loss, and throughput are independent scenario inputs; the
propagation model lands with BL-041 / BL-048); a weaker
``throughput is zero when not live`` invariant stands in.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nous.estimators.position import PositionEKF
from nous.state.machine import GuardDenied, Mode, StateMachine
from nous.subsystems.comms import CommsSubsystem
from nous.subsystems.compute import ComputeSubsystem
from nous.subsystems.power import PowerSubsystem
from nous.subsystems.storage import StorageSubsystem
from nous.subsystems.thermal import ThermalSubsystem
from nous.types import Observation


def _minimal_profile() -> Mapping[str, Any]:
    return {
        "name": "invariants-test",
        "power": {"battery_wh": 100.0, "voltage_v_nominal": 14.4},
        "compute": {
            "draw_w_idle": 5.0,
            "draw_w_load": 50.0,
            "load_curve": [
                {"load_pct": 0.0, "draw_w": 5.0},
                {"load_pct": 50.0, "draw_w": 25.0},
                {"load_pct": 100.0, "draw_w": 50.0},
            ],
        },
        "thermal": {
            "ambient_c_default": 20.0,
            "junction_temp_throttle": 90.0,
            "enclosure_to_ambient_resistance_c_per_w": 0.5,
        },
        "comms": {
            "links": [
                {
                    "id": "lte",
                    "bandwidth_bps": 20_000_000,
                    "rssi_dbm_nominal": -75,
                    "loss_pct_nominal": 0.5,
                    "max_age_s": 30.0,
                }
            ]
        },
    }


# --- Compute: draw_w monotonic in load_pct ---


@given(
    load_a=st.floats(min_value=0.0, max_value=100.0),
    load_b=st.floats(min_value=0.0, max_value=100.0),
)
def test_compute_draw_monotonic_in_load(load_a: float, load_b: float) -> None:
    """At constant throttle state (no throttling), draw_w must be
    monotonic non-decreasing in load_pct. The piecewise-linear
    load_curve in the profile guarantees this; a regression that
    introduces a curve dip fails here."""
    c = ComputeSubsystem(_minimal_profile())
    c.set_load_pct(load_a)
    draw_a = c.draw_w
    c.set_load_pct(load_b)
    draw_b = c.draw_w
    if load_a <= load_b:
        assert draw_a <= draw_b + 1e-9
    else:
        assert draw_a >= draw_b - 1e-9


# --- Power: SoC monotone non-increasing under sustained discharge ---


@given(load_w=st.floats(min_value=1.0, max_value=50.0))
def test_power_soc_monotone_non_increasing_under_discharge(load_w: float) -> None:
    """With a positive discharge load and no charge input, SoC
    must drop or stay the same on every tick. Any tick that
    raises SoC under discharge breaks the conservation invariant
    the self-model relies on for the endurance capability claim."""
    p = PowerSubsystem(_minimal_profile())
    p.set_load_w(load_w)
    p.set_charge_w(0.0)
    soc_history = [p.soc_pct]
    for _ in range(20):
        p.step(1.0)
        soc_history.append(p.soc_pct)
    for prev, curr in pairwise(soc_history):
        assert curr <= prev + 1e-9


# --- Thermal: zero load + constant ambient -> convergence to ambient ---


@given(ambient_c=st.floats(min_value=-20.0, max_value=40.0))
def test_thermal_zero_load_converges_to_ambient(ambient_c: float) -> None:
    """With load=0 and ambient held constant, both junction and
    enclosure temperatures must approach the ambient monotonically.
    A regression that introduces a thermal source (a stuck heater,
    a stale load) fails here."""
    t = ThermalSubsystem(_minimal_profile())
    t.set_ambient_c(ambient_c)
    t.set_load_w(0.0)
    # Long enough to reach steady state on the lumped two-mass
    # model with default thermal resistances.
    for _ in range(5000):
        t.step(1.0)
    # Within 0.5 C of ambient is steady-state for the default
    # parameters; tightening would risk integrator overshoot.
    assert abs(t.junction_c - ambient_c) < 0.5
    assert abs(t.enclosure_c - ambient_c) < 0.5


# --- Comms link envelope: age monotone in ticks-since-tx ---


@given(ticks=st.integers(min_value=1, max_value=25))
def test_comms_link_age_monotone_in_ticks_since_tx(ticks: int) -> None:
    """Link age increases monotonically with tick count when no
    transmission resets the counter. A regression that resets age
    on the wrong condition would let a stale link advertise
    freshness; this invariant catches it."""
    c = CommsSubsystem(_minimal_profile())
    link = c.link("lte")
    assert link is not None
    ages = [link.age_s]
    for _ in range(ticks):
        c.step(1.0)
        ages.append(link.age_s)
    for prev, curr in pairwise(ages):
        assert curr >= prev


def test_comms_tx_resets_age() -> None:
    """The complement of the previous invariant: a transmission
    must reset age to zero. Without this, the freshness guard
    in the encoder paths never trips on a long-running link."""
    c = CommsSubsystem(_minimal_profile())
    c.step(10.0)
    link = c.link("lte")
    assert link is not None
    assert link.age_s == pytest.approx(10.0)
    c.tx("lte", 1024)
    link_after = c.link("lte")
    assert link_after is not None
    assert link_after.age_s == pytest.approx(0.0)


# --- Power: Peukert capacity-vs-current ---


@given(
    low_load_w=st.floats(min_value=1.0, max_value=10.0),
    high_load_w=st.floats(min_value=20.0, max_value=50.0),
)
def test_power_peukert_higher_current_drains_faster(
    low_load_w: float, high_load_w: float
) -> None:
    """Peukert's law: at constant temperature, the effective
    capacity is monotonically non-increasing in discharge current.
    Two batteries with identical starting state, run for the same
    duration: the one under the higher discharge load drops to a
    lower SoC."""
    p_low = PowerSubsystem(_minimal_profile())
    p_high = PowerSubsystem(_minimal_profile())
    p_low.set_load_w(low_load_w)
    p_high.set_load_w(high_load_w)
    p_low.set_charge_w(0.0)
    p_high.set_charge_w(0.0)
    for _ in range(60):
        p_low.step(1.0)
        p_high.step(1.0)
    assert p_high.soc_pct <= p_low.soc_pct + 1e-9


# --- Thermal: junction above enclosure under load ---


def test_thermal_junction_above_enclosure_under_sustained_load() -> None:
    """Two-mass lumped model contract: with positive load and the
    junction's faster time constant, junction temperature is
    strictly above enclosure temperature once the system has had
    time to differentiate. A regression that wires the load into
    the enclosure node first (or that swaps the time constants)
    fails here."""
    t = ThermalSubsystem(_minimal_profile())
    t.set_ambient_c(20.0)
    t.set_load_w(40.0)
    for _ in range(300):
        t.step(1.0)
    assert t.junction_c > t.enclosure_c


# --- Compute: throttling never increases draw or load ---


@given(requested_pct=st.floats(min_value=50.0, max_value=100.0))
def test_compute_throttling_never_increases_draw_or_load(
    requested_pct: float,
) -> None:
    """The thermal-throttle clamp must only reduce the delivered
    load (and therefore the electrical draw). A regression that
    inverts the clamp direction would *increase* draw on
    throttle and fails the invariant immediately."""
    c = ComputeSubsystem(_minimal_profile())
    c.set_load_pct(requested_pct)
    unthrottled_load = c.load_pct
    unthrottled_draw = c.draw_w

    c.set_thermal_throttle(throttling=True)
    throttled_load = c.load_pct
    throttled_draw = c.draw_w

    assert throttled_load <= unthrottled_load + 1e-9
    assert throttled_draw <= unthrottled_draw + 1e-9


# --- Position EKF: covariance growth + shrink ---


@given(dt_s=st.floats(min_value=0.1, max_value=10.0))
def test_position_ekf_predict_only_covariance_grows(dt_s: float) -> None:
    """Without an observation, the EKF's belief gets less certain
    over time. Every covariance entry is monotone non-decreasing
    under ``predict(dt)`` per the existing
    ``test_estimator_properties`` contract; this case lifts the
    invariant into the subsystem suite at the position-EKF level."""
    ekf = PositionEKF()
    before = dict(ekf.state().covariance)
    ekf.predict(dt_s)
    after = dict(ekf.state().covariance)
    for key, prev in before.items():
        assert after[key] >= prev - 1e-12, f"covariance {key} shrank under predict"


def test_position_ekf_update_shrinks_covariance() -> None:
    """The complement: an observation tightens the posterior. The
    EKF was grown via repeated predicts; a confident observation
    pulls every channel covariance below its pre-update value."""
    ekf = PositionEKF()
    for _ in range(10):
        ekf.predict(1.0)
    grown = dict(ekf.state().covariance)
    ekf.update(
        Observation(
            source="position",
            ts_s=10.0,
            payload={"lat": 45.0, "lon": 12.0, "alt_m": 100.0},
            noise={"lat_sigma": 1e-5, "lon_sigma": 1e-5, "alt_m_sigma": 1.0},
        )
    )
    after = dict(ekf.state().covariance)
    for key, prev in grown.items():
        assert after[key] <= prev + 1e-12, f"covariance {key} grew under update"


# --- Storage: used_gib and wear_pct monotone non-decreasing ---


@given(
    write_gib=st.floats(min_value=0.0, max_value=100.0),
)
def test_storage_used_gib_monotone_under_writes(write_gib: float) -> None:
    """``used_gib`` only grows under ``write()`` (the call clamps
    negative inputs to zero). A regression that lets a write
    decrement the counter would break the wear accounting that
    the self-model's storage capability claim depends on."""
    s = StorageSubsystem(_minimal_profile())
    before = s.used_gib
    s.write(write_gib)
    assert s.used_gib >= before - 1e-12


@given(
    writes=st.lists(
        st.floats(min_value=0.0, max_value=50.0), min_size=1, max_size=10
    ),
)
def test_storage_wear_pct_monotone_under_writes(writes: list[float]) -> None:
    """NAND wear is cumulative; each write either adds to the
    counter or (when the device is full) leaves it untouched. The
    counter never decreases."""
    s = StorageSubsystem(_minimal_profile())
    history = [s.wear_pct]
    for gib in writes:
        s.write(gib)
        history.append(s.wear_pct)
    for prev, curr in pairwise(history):
        assert curr >= prev - 1e-12


# --- Comms: throughput is zero when the link is not live ---


def test_comms_link_estimate_throughput_zero_when_not_live() -> None:
    """The full SNR-to-throughput propagation model lands with
    BL-041 / BL-048; today RSSI, loss, and throughput are
    independent scenario inputs. The weaker invariant the
    subsystem does enforce: ``LinkEstimate.throughput_bps`` is
    zero when the link is not live, regardless of what the
    scenario set the raw throughput to. A regression that
    advertises a stale throughput on a dead link breaks the
    self-model's comms capability claim."""
    c = CommsSubsystem(_minimal_profile())
    c.set_link_state("lte", throughput_bps=20_000_000.0, connected=False)
    estimates = {est.link_id: est for est in c.link_estimates()}
    lte_estimate = estimates["lte"]
    assert lte_estimate.throughput_bps == 0.0


# --- FSM: transition closure ---


@given(trigger=st.sampled_from(["boot", "ready", "shutdown"]))
def test_fsm_transition_returns_match_current(trigger: str) -> None:
    """``transition()`` is never a no-op that lies: after a
    successful call, the returned mode equals ``fsm.current``.
    A regression that updates the FSM's internal state but
    returns a stale mode (or vice versa) fails immediately."""
    fsm = StateMachine()
    if not fsm.can(trigger):
        # Not applicable from STOWED for some triggers; skip.
        return
    returned = fsm.transition(trigger)
    assert returned is fsm.current


def test_fsm_successful_unguarded_transition_advances_history() -> None:
    """Every admitted, unguarded transition appends one entry to
    ``history``. A guarded refusal must not (covered separately
    in ``test_state_machine_guards`` and pinned via the existing
    H1 regression set)."""
    fsm = StateMachine()
    initial = len(fsm.history())
    fsm.transition("boot")
    after_one = len(fsm.history())
    fsm.transition("ready")
    after_two = len(fsm.history())
    assert after_one == initial + 1
    assert after_two == after_one + 1


def test_fsm_refused_transition_does_not_advance_history() -> None:
    """SC-2 refuses an IDLE -> MISSION without thermal context.
    The refusal must NOT touch ``history``; that surface is
    reserved for transitions that actually traversed."""
    fsm = StateMachine()
    fsm.transition("boot")
    fsm.transition("ready")
    history_before = list(fsm.history())
    with pytest.raises(GuardDenied):
        fsm.transition("mission")  # no thermal context -> refused
    assert fsm.current is Mode.IDLE
    assert fsm.history() == history_before
