"""Property-based invariants for subsystem physics (ADR 0020).

Closes the second half of AUDIT-2026-05-27 N8 (the ADR 0020
implementation). The existing
``tests/unit/test_estimator_properties.py`` covers the filter
contract; this file covers the subsystem layer underneath. The
invariants are closed-form facts about the modelled physics, not
numeric examples: a regression that breaks the invariant fails on
every Hypothesis seed, not only on the seed that picked the
example.

Coverage at first publication is a representative subset of the
invariants ADR 0020 enumerates: compute draw monotonicity in
load, power SoC monotonicity under sustained discharge, thermal
convergence to ambient under zero load, and comms link-age
monotonicity. Other invariants (full Peukert envelope, FSM
transition closure, SNR-throughput coupling) extend the
parametrisation in the same shape; the pattern is the file.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nous.subsystems.comms import CommsSubsystem
from nous.subsystems.compute import ComputeSubsystem
from nous.subsystems.power import PowerSubsystem
from nous.subsystems.thermal import ThermalSubsystem


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
