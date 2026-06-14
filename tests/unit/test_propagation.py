"""Unit tests for the BL-048 RF link-budget physics (ADR 0053)."""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from nous.subsystems.propagation import (
    LinkPropagation,
    capacity_bps,
    free_space_path_loss_db,
    received_power_dbm,
    rssi_to_loss_pct,
    slant_range_m,
    solve_link_budget,
)


def test_slant_range_zero_at_same_point() -> None:
    assert slant_range_m(47.0, 13.0, 500.0, 47.0, 13.0, 500.0) == 0.0


def test_slant_range_grows_with_separation() -> None:
    near = slant_range_m(47.0, 13.0, 500.0, 47.01, 13.0, 500.0)
    far = slant_range_m(47.0, 13.0, 500.0, 47.05, 13.0, 500.0)
    assert 0.0 < near < far


def test_slant_range_includes_altitude() -> None:
    flat = slant_range_m(47.0, 13.0, 500.0, 47.0, 13.0, 500.0)
    tall = slant_range_m(47.0, 13.0, 500.0, 47.0, 13.0, 1500.0)
    assert flat == 0.0
    assert math.isclose(tall, 1000.0, rel_tol=1e-6)


def test_path_loss_grows_with_range_and_frequency() -> None:
    near = free_space_path_loss_db(1_000.0, 2.4e9)
    far = free_space_path_loss_db(10_000.0, 2.4e9)
    high = free_space_path_loss_db(1_000.0, 5.0e9)
    assert far > near
    assert high > near
    # A decade of range is 20 dB of free-space loss.
    assert math.isclose(far - near, 20.0, abs_tol=1e-6)


def test_path_loss_clamps_at_minimum_range() -> None:
    at_zero = free_space_path_loss_db(0.0, 2.4e9)
    at_one = free_space_path_loss_db(1.0, 2.4e9)
    assert math.isfinite(at_zero)
    assert at_zero == at_one


def test_received_power_is_the_link_budget_sum() -> None:
    rx = received_power_dbm(30.0, 2.0, 2.0, 100.0, 5.0, 1.0)
    assert math.isclose(rx, 30.0 + 2.0 + 2.0 - 100.0 - 5.0 - 1.0)


def test_capacity_zero_below_floor_full_above_full() -> None:
    assert capacity_bps(1_000_000.0, 0.0, 3.0, 25.0) == 0.0
    assert capacity_bps(1_000_000.0, 30.0, 3.0, 25.0) == 1_000_000.0


def test_capacity_ramps_monotonically_in_snr() -> None:
    low = capacity_bps(1_000_000.0, 8.0, 3.0, 25.0)
    mid = capacity_bps(1_000_000.0, 14.0, 3.0, 25.0)
    high = capacity_bps(1_000_000.0, 20.0, 3.0, 25.0)
    assert 0.0 < low < mid < high < 1_000_000.0


def test_capacity_degenerate_ramp_is_a_step() -> None:
    assert capacity_bps(1_000.0, 10.0, 10.0, 10.0) == 1_000.0
    assert capacity_bps(1_000.0, 9.9, 10.0, 10.0) == 0.0


def test_rssi_to_loss_floor_at_good_full_at_sensitivity() -> None:
    assert rssi_to_loss_pct(-60.0, -85.0, -110.0, 1.0) == 1.0
    assert rssi_to_loss_pct(-120.0, -85.0, -110.0, 1.0) == 100.0


def test_rssi_to_loss_is_monotone_as_signal_falls() -> None:
    strong = rssi_to_loss_pct(-88.0, -85.0, -110.0, 1.0)
    mid = rssi_to_loss_pct(-97.0, -85.0, -110.0, 1.0)
    weak = rssi_to_loss_pct(-106.0, -85.0, -110.0, 1.0)
    assert strong < mid < weak


def test_from_profile_returns_none_without_block_or_peer() -> None:
    assert LinkPropagation.from_profile({"id": "x"}) is None
    assert LinkPropagation.from_profile({"propagation": {}}) is None
    assert (
        LinkPropagation.from_profile({"propagation": {"peer": {"lat": 1.0}}}) is None
    )


def test_from_profile_parses_block_with_defaults() -> None:
    prop = LinkPropagation.from_profile(
        {
            "propagation": {
                "peer": {"lat": 47.0, "lon": 13.0, "alt_m": 600.0},
                "tx_power_dbm": 33.0,
                "frequency_hz": 9.0e8,
            }
        }
    )
    assert prop is not None
    assert prop.peer_lat == 47.0
    assert prop.tx_power_dbm == 33.0
    assert prop.frequency_hz == 9.0e8
    # An unspecified field takes its default.
    assert prop.rx_gain_dbi == 2.0


def _demo_prop() -> LinkPropagation:
    return LinkPropagation(
        peer_lat=47.0,
        peer_lon=13.0,
        peer_alt_m=600.0,
        tx_power_dbm=33.0,
        frequency_hz=9.0e8,
        good_rssi_dbm=-85.0,
        sensitivity_dbm=-115.0,
        snr_floor_db=3.0,
        snr_full_db=25.0,
        noise_floor_dbm=-110.0,
    )


def test_solve_link_budget_degrades_with_distance() -> None:
    prop = _demo_prop()
    near = solve_link_budget(
        prop, device_lat=47.0, device_lon=13.01, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    far = solve_link_budget(
        prop, device_lat=47.0, device_lon=13.20, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    assert far.range_m > near.range_m
    assert far.path_loss_db > near.path_loss_db
    assert far.rssi_dbm < near.rssi_dbm
    assert far.snr_db < near.snr_db
    assert far.capacity_bps <= near.capacity_bps
    assert far.loss_pct >= near.loss_pct


@given(
    near_lon=st.floats(13.001, 13.05),
    extra=st.floats(0.001, 0.30),
)
def test_capacity_monotone_and_loss_monotone_in_range(
    near_lon: float, extra: float
) -> None:
    """ADR 0020 / ADR 0053: moving away never increases capacity nor lowers loss."""
    prop = _demo_prop()
    near = solve_link_budget(
        prop, device_lat=47.0, device_lon=near_lon, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    far = solve_link_budget(
        prop, device_lat=47.0, device_lon=near_lon + extra, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    assert far.range_m >= near.range_m
    assert far.capacity_bps <= near.capacity_bps + 1e-6
    assert far.loss_pct >= near.loss_pct - 1e-9
