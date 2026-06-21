"""Unit tests for the BL-048 RF link-budget physics (ADR 0053)."""

from __future__ import annotations

import math

import numpy as np
from hypothesis import given
from hypothesis import strategies as st
from pytest import approx as pytest_approx

from nous.subsystems.propagation import (
    LinkPropagation,
    antenna_gain_offset_db,
    bearing_deg,
    bullington_diffraction_db,
    capacity_bps,
    free_space_path_loss_db,
    knife_edge_diffraction_db,
    log_distance_path_loss_db,
    received_power_dbm,
    rician_fade_db,
    rssi_to_loss_pct,
    slant_range_m,
    solve_link_budget,
    thermal_noise_floor_dbm,
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


# -- BL-088 / ADR 0054: higher-fidelity upgrades --------------------------


def test_log_distance_reduces_to_free_space_at_exponent_two() -> None:
    assert log_distance_path_loss_db(5_000.0, 2.4e9, 2.0) == pytest_approx(
        free_space_path_loss_db(5_000.0, 2.4e9)
    )


def test_log_distance_is_steeper_above_exponent_two() -> None:
    free = log_distance_path_loss_db(5_000.0, 2.4e9, 2.0)
    urban = log_distance_path_loss_db(5_000.0, 2.4e9, 3.0)
    forest = log_distance_path_loss_db(5_000.0, 2.4e9, 4.0)
    assert free < urban < forest


def test_knife_edge_zero_below_los_and_grows_with_height() -> None:
    below = knife_edge_diffraction_db(400.0, 500.0, 2_000.0, 3_000.0, 2.4e9)
    grazing = knife_edge_diffraction_db(500.0, 500.0, 2_000.0, 3_000.0, 2.4e9)
    tall = knife_edge_diffraction_db(600.0, 500.0, 2_000.0, 3_000.0, 2.4e9)
    assert below == 0.0
    assert 0.0 <= grazing < tall


def test_knife_edge_grazing_is_about_six_db() -> None:
    # At v = 0 (obstruction exactly on the line of sight) the ITU loss is ~6 dB.
    grazing = knife_edge_diffraction_db(500.0, 500.0, 2_000.0, 3_000.0, 2.4e9)
    assert grazing == pytest_approx(6.0, abs=0.1)


def test_antenna_offset_zero_at_boresight_floored_at_back() -> None:
    assert antenna_gain_offset_db(90.0, 90.0, 30.0, 20.0) == 0.0
    # -3 dB at the half-beamwidth off boresight.
    assert antenna_gain_offset_db(120.0, 90.0, 30.0, 20.0) == pytest_approx(-3.0)
    # Floored at the back-lobe attenuation.
    assert antenna_gain_offset_db(270.0, 90.0, 30.0, 20.0) == -20.0
    # Symmetric about boresight, and wraps across 0/360 (340 vs 10 is 30 apart).
    assert antenna_gain_offset_db(60.0, 90.0, 30.0, 20.0) == pytest_approx(-3.0)
    assert antenna_gain_offset_db(340.0, 10.0, 30.0, 20.0) == pytest_approx(-3.0)


def test_thermal_noise_floor_formula_and_monotonicity() -> None:
    # -174 dBm/Hz + 10 log10(1e6) + 5 dB NF ~= -109 dBm.
    assert thermal_noise_floor_dbm(1e6, 5.0) == pytest_approx(-109.0, abs=0.1)
    # A wider channel raises the floor by 3 dB per doubling.
    assert thermal_noise_floor_dbm(2e6, 0.0) - thermal_noise_floor_dbm(
        1e6, 0.0
    ) == pytest_approx(3.0, abs=0.05)


def test_rician_fade_is_lower_variance_at_higher_k() -> None:
    rng = np.random.default_rng(0)
    rayleigh = [rician_fade_db(rng, 0.0) for _ in range(4000)]
    near_los = [rician_fade_db(rng, 15.0) for _ in range(4000)]
    assert float(np.var(rayleigh)) > float(np.var(near_los))
    # Fading is a net loss on average (the log is concave on a unit-mean power).
    assert float(np.mean(rayleigh)) > 0.0


def test_rician_fade_is_deterministic_under_seed() -> None:
    a = [rician_fade_db(np.random.default_rng(3), 6.0) for _ in range(3)]
    b = [rician_fade_db(np.random.default_rng(3), 6.0) for _ in range(3)]
    assert a == b


def test_bearing_cardinal_directions() -> None:
    assert bearing_deg(47.0, 13.0, 48.0, 13.0) == pytest_approx(0.0, abs=0.5)  # north
    assert bearing_deg(47.0, 13.0, 47.0, 13.1) == pytest_approx(90.0, abs=0.5)  # east


def test_solve_link_budget_obstruction_adds_diffraction_loss() -> None:
    clear = LinkPropagation(peer_lat=47.0, peer_lon=13.10, peer_alt_m=500.0)
    blocked = LinkPropagation(
        peer_lat=47.0,
        peer_lon=13.10,
        peer_alt_m=500.0,
        obstruction_distance_m=4_000.0,
        obstruction_height_m=900.0,  # a ridge well above the 500 m line of sight
    )
    a = solve_link_budget(
        clear, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    b = solve_link_budget(
        blocked, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    assert a.diffraction_loss_db == 0.0
    assert b.diffraction_loss_db > 0.0
    assert b.rssi_dbm < a.rssi_dbm
    assert b.path_loss_db > a.path_loss_db


def test_solve_link_budget_off_boresight_antenna_lowers_rssi() -> None:
    # Peer due east (bearing ~90); a boresight pointed north sees it off-axis.
    pointed = LinkPropagation(
        peer_lat=47.0, peer_lon=13.10, peer_alt_m=500.0,
        antenna_boresight_deg=90.0, antenna_half_beamwidth_deg=30.0,
    )
    turned = LinkPropagation(
        peer_lat=47.0, peer_lon=13.10, peer_alt_m=500.0,
        antenna_boresight_deg=0.0, antenna_half_beamwidth_deg=30.0,
    )
    on = solve_link_budget(
        pointed, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    off = solve_link_budget(
        turned, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    # The peer is essentially on boresight (a due-east great-circle bearing is
    # ~90 but not exactly), so the offset is negligible rather than exactly 0.
    assert on.antenna_offset_db == pytest_approx(0.0, abs=1e-3)
    assert off.antenna_offset_db < -1.0
    assert off.rssi_dbm < on.rssi_dbm


def test_solve_link_budget_ktb_noise_floor_when_channel_bandwidth_set() -> None:
    base = LinkPropagation(peer_lat=47.0, peer_lon=13.10, peer_alt_m=500.0)
    ktb = LinkPropagation(
        peer_lat=47.0, peer_lon=13.10, peer_alt_m=500.0,
        channel_bandwidth_hz=5e6, noise_figure_db=6.0,
    )
    b1 = solve_link_budget(
        base, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    b2 = solve_link_budget(
        ktb, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    assert b1.noise_floor_dbm == pytest_approx(-100.0)  # the ADR 0053 constant
    assert b2.noise_floor_dbm == pytest_approx(
        thermal_noise_floor_dbm(5e6, 6.0)
    )


def test_solve_link_budget_fast_fade_only_shifts_rssi() -> None:
    prop = LinkPropagation(peer_lat=47.0, peer_lon=13.10, peer_alt_m=500.0)
    quiet = solve_link_budget(
        prop, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    faded = solve_link_budget(
        prop, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0, fast_fade_db=10.0,
    )
    assert faded.rssi_dbm == pytest_approx(quiet.rssi_dbm - 10.0)


def test_bullington_reduces_to_single_knife_edge() -> None:
    # BL-089: one interior obstacle. The Bullington equivalent edge lands on it,
    # so the loss equals the single knife-edge formula exactly (2 d / (d1 d2) ==
    # 2 (1/d1 + 1/d2) when d1 + d2 = d).
    profile = [(0.0, 500.0), (2_000.0, 600.0), (5_000.0, 500.0)]
    single = knife_edge_diffraction_db(600.0, 500.0, 2_000.0, 3_000.0, 2.4e9)
    multi = bullington_diffraction_db(profile, 500.0, 500.0, 2.4e9)
    assert multi == pytest_approx(single)


def test_bullington_zero_below_line_of_sight() -> None:
    profile = [(0.0, 500.0), (2_500.0, 480.0), (5_000.0, 500.0)]
    assert bullington_diffraction_db(profile, 500.0, 500.0, 2.4e9) == 0.0


def test_bullington_grows_with_obstacle_height() -> None:
    short = bullington_diffraction_db(
        [(0.0, 500.0), (2_500.0, 560.0), (5_000.0, 500.0)], 500.0, 500.0, 2.4e9
    )
    tall = bullington_diffraction_db(
        [(0.0, 500.0), (2_500.0, 660.0), (5_000.0, 500.0)], 500.0, 500.0, 2.4e9
    )
    assert tall > short > 0.0


def test_bullington_handles_multiple_edges() -> None:
    # Two ridges between the endpoints: the path is obstructed, so the multi-edge
    # method returns a positive loss (the single knife-edge model sees one edge).
    two = bullington_diffraction_db(
        [(0.0, 500.0), (1_500.0, 640.0), (3_500.0, 620.0), (5_000.0, 500.0)],
        500.0,
        500.0,
        2.4e9,
    )
    assert two > 0.0


def test_solve_link_budget_terrain_replaces_single_knife_edge() -> None:
    # use_terrain routes diffraction through the sampled terrain profile; a clear
    # profile (terrain below the LoS) yields no diffraction, a ridge yields loss.
    prop = LinkPropagation(
        peer_lat=47.0, peer_lon=13.10, peer_alt_m=500.0, use_terrain=True
    )
    clear_profile = [(0.0, 500.0), (4_000.0, 470.0), (8_000.0, 500.0)]
    ridge_profile = [(0.0, 500.0), (4_000.0, 700.0), (8_000.0, 500.0)]
    clear = solve_link_budget(
        prop, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0, terrain_profile=clear_profile,
    )
    blocked = solve_link_budget(
        prop, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0, terrain_profile=ridge_profile,
    )
    assert clear.diffraction_loss_db == 0.0
    assert blocked.diffraction_loss_db > 0.0
    assert blocked.path_loss_db > clear.path_loss_db


def test_from_profile_parses_higher_fidelity_fields() -> None:
    prop = LinkPropagation.from_profile(
        {
            "propagation": {
                "peer": {"lat": 47.0, "lon": 13.0, "alt_m": 600.0},
                "path_loss_exponent": 3.2,
                "obstruction_distance_m": 4_000.0,
                "obstruction_height_m": 850.0,
                "channel_bandwidth_hz": 5e6,
                "noise_figure_db": 6.0,
                "antenna_boresight_deg": 270.0,
                "antenna_half_beamwidth_deg": 25.0,
                "antenna_front_to_back_db": 18.0,
                "rician_k_db": 8.0,
            }
        }
    )
    assert prop is not None
    assert prop.path_loss_exponent == 3.2
    assert prop.obstruction_distance_m == 4_000.0
    assert prop.channel_bandwidth_hz == 5e6
    assert prop.antenna_boresight_deg == 270.0
    assert prop.rician_k_db == 8.0
    # An unset higher-fidelity field keeps its ADR 0053 default.
    assert LinkPropagation.from_profile(
        {"propagation": {"peer": {"lat": 1.0, "lon": 2.0}}}
    ).path_loss_exponent == 2.0  # type: ignore[union-attr]


def test_from_profile_sanitizes_non_physical_noise_config() -> None:
    """PR #139 review: a non-positive channel bandwidth reads as unset and a
    negative noise figure is clamped, so bad config cannot flatter the SNR."""
    prop = LinkPropagation.from_profile(
        {
            "propagation": {
                "peer": {"lat": 47.0, "lon": 13.0},
                "channel_bandwidth_hz": -1.0,
                "noise_figure_db": -3.0,
            }
        }
    )
    assert prop is not None
    assert prop.channel_bandwidth_hz is None
    assert prop.noise_figure_db == 0.0


def test_solve_link_budget_fails_conservative_on_bad_noise_config() -> None:
    """A directly-built LinkPropagation with a non-positive bandwidth must fall
    back to the constant floor rather than the optimistic 1 Hz kTB floor."""
    bad = LinkPropagation(
        peer_lat=47.0,
        peer_lon=13.10,
        peer_alt_m=500.0,
        noise_floor_dbm=-100.0,
        channel_bandwidth_hz=0.0,
        noise_figure_db=-50.0,
    )
    budget = solve_link_budget(
        bad, device_lat=47.0, device_lon=13.0, device_alt_m=500.0,
        bandwidth_bps=2_000_000.0,
    )
    assert budget.noise_floor_dbm == pytest_approx(-100.0)
