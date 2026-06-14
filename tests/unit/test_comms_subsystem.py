"""Comms subsystem: link parsing, age-out, scenario overrides, state derivation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nous.state.comms_state import CommsState
from nous.subsystems.comms import CommsSubsystem


def _profile(*links: Mapping[str, Any]) -> Mapping[str, Any]:
    default: list[Mapping[str, Any]] = list(links) or [
        {
            "id": "lte",
            "bandwidth_bps": 20_000_000,
            "rssi_dbm_nominal": -75,
            "loss_pct_nominal": 0.5,
            "max_age_s": 30.0,
        },
        {
            "id": "lora",
            "bandwidth_bps": 50_000,
            "rssi_dbm_nominal": -110,
            "loss_pct_nominal": 2.0,
            "max_age_s": 120.0,
        },
    ]
    return {"comms": {"links": default}}


def test_parses_links_from_profile() -> None:
    c = CommsSubsystem(_profile())
    assert c.link_ids == ["lte", "lora"]
    lte = c.link("lte")
    assert lte is not None
    assert lte.bandwidth_bps == pytest.approx(20_000_000)


def test_links_start_connected_with_nominal_envelope() -> None:
    c = CommsSubsystem(_profile())
    lte = c.link("lte")
    assert lte is not None
    assert lte.is_live() is True
    assert lte.rssi_dbm == pytest.approx(-75)
    assert lte.loss_pct == pytest.approx(0.5)


def test_age_out_after_max_age_s() -> None:
    c = CommsSubsystem(_profile())
    c.step(31.0)  # past LTE max_age_s = 30
    lte = c.link("lte")
    assert lte is not None
    assert lte.is_live() is False
    assert lte.throughput_bps == pytest.approx(0.0)


def test_age_out_is_counted_and_stamped() -> None:
    # COMMS-2: the connected -> aged-out transition is stamped so a controller
    # can see the drop (and a flap a coarse poll missed) via comms_status.
    c = CommsSubsystem(_profile())
    c.step(31.0)
    lte = c.link("lte")
    assert lte is not None
    assert lte.age_out_count == 1
    assert lte.last_aged_out_at_s == pytest.approx(31.0)
    # Staying aged out across further ticks does not re-count the transition.
    c.step(5.0)
    assert lte.age_out_count == 1
    # A transmission revives the link; the next age-out is a fresh transition.
    c.tx("lte", 1000)
    c.step(31.0)
    assert lte.age_out_count == 2
    assert lte.last_aged_out_at_s == pytest.approx(67.0)


def test_age_out_count_surfaces_in_truth() -> None:
    c = CommsSubsystem(_profile())
    c.step(31.0)
    truth = c.truth()
    lte_row = next(row for row in truth["links"] if row["link_id"] == "lte")
    assert lte_row["age_out_count"] == 1
    assert lte_row["last_aged_out_at_s"] == pytest.approx(31.0)


def test_forced_down_link_does_not_count_as_age_out() -> None:
    # A controller-forced disconnect is not an age-out; the counter stays 0.
    c = CommsSubsystem(_profile())
    c.set_link_state("lte", connected=False)
    c.step(31.0)
    lte = c.link("lte")
    assert lte is not None
    assert lte.age_out_count == 0
    assert lte.last_aged_out_at_s is None


def test_forced_down_then_cleared_while_stale_does_not_count() -> None:
    # A link forced down, left to go stale, then released is not a genuine
    # live -> aged-out transition: clearing the override must not bump the
    # counter just because age_s exceeded max_age_s while the link was forced
    # down (it was never live in the unforced regime). Gating on is_live()
    # rather than the raw connected flag is what makes this hold.
    c = CommsSubsystem(_profile())
    c.set_link_state("lte", connected=False)
    c.step(60.0)  # age climbs well past max_age_s while forced down
    c.clear_link_override("lte")
    c.step(1.0)  # first unforced step finds the link already stale
    lte = c.link("lte")
    assert lte is not None
    assert lte.is_live() is False
    assert lte.age_out_count == 0
    assert lte.last_aged_out_at_s is None


def test_tx_resets_age_and_marks_live() -> None:
    c = CommsSubsystem(_profile())
    c.step(31.0)
    accepted = c.tx("lte", 1000)
    assert accepted == 1000
    lte = c.link("lte")
    assert lte is not None
    assert lte.is_live() is True
    assert lte.age_s == pytest.approx(0.0)


def test_tx_throughput_is_a_rate_over_the_send_interval() -> None:
    # COMMS-3: throughput_bps is bits / elapsed-since-last-send, not the raw
    # packet size in bits. 1000 bytes (8000 bits) sent after a 2 s gap is a
    # 4000 bps rate, not 8000.
    c = CommsSubsystem(_profile())
    c.step(2.0)
    c.tx("lte", 1000)
    lte = c.link("lte")
    assert lte is not None
    assert lte.throughput_bps == pytest.approx(4000.0)


def test_tx_throughput_caps_at_link_bandwidth() -> None:
    # A burst in near-zero time cannot beat the link's capacity.
    c = CommsSubsystem(_profile())
    c.step(0.001)
    c.tx("lte", 10_000_000)
    lte = c.link("lte")
    assert lte is not None
    assert lte.throughput_bps == pytest.approx(lte.bandwidth_bps)


def test_tx_first_send_reports_link_bandwidth() -> None:
    # No elapsed time on the first send -> report capacity, not divide by zero.
    c = CommsSubsystem(_profile())
    c.tx("lte", 1500)
    lte = c.link("lte")
    assert lte is not None
    assert lte.throughput_bps == pytest.approx(lte.bandwidth_bps)


def test_tx_unknown_link_returns_zero() -> None:
    c = CommsSubsystem(_profile())
    assert c.tx("nonexistent", 500) == 0


def test_tx_zero_bytes_ignored() -> None:
    c = CommsSubsystem(_profile())
    assert c.tx("lte", 0) == 0


def test_forced_disconnect_persists_through_tx() -> None:
    c = CommsSubsystem(_profile())
    c.set_link_state("lte", connected=False)
    accepted = c.tx("lte", 1000)
    assert accepted == 0
    lte = c.link("lte")
    assert lte is not None
    assert lte.is_live() is False


def test_clear_link_override_releases_forced_state() -> None:
    c = CommsSubsystem(_profile())
    c.set_link_state("lte", connected=False)
    c.clear_link_override("lte")
    lte = c.link("lte")
    assert lte is not None
    assert lte.forced_state is None
    assert lte.is_live() is True


def test_set_link_state_rssi_and_loss_clamp() -> None:
    c = CommsSubsystem(_profile())
    c.set_link_state("lte", rssi_dbm=-90.0, loss_pct=250.0, throughput_bps=-5.0)
    lte = c.link("lte")
    assert lte is not None
    assert lte.rssi_dbm == pytest.approx(-90.0)
    assert lte.loss_pct == pytest.approx(100.0)
    assert lte.throughput_bps == pytest.approx(0.0)


def test_derive_state_all_links_live() -> None:
    c = CommsSubsystem(_profile())
    label, _ = c.derive_state()
    assert label is CommsState.CONNECTED


def test_derive_state_all_links_down() -> None:
    c = CommsSubsystem(_profile())
    c.set_link_state("lte", connected=False)
    c.set_link_state("lora", connected=False)
    label, _ = c.derive_state()
    assert label is CommsState.DENIED


def test_derive_state_limited_when_one_link_unhealthy() -> None:
    c = CommsSubsystem(_profile())
    c.set_link_state("lora", loss_pct=80.0)
    label, _ = c.derive_state()
    assert label is CommsState.LIMITED


def test_link_estimates_match_subsystem_truth() -> None:
    c = CommsSubsystem(_profile())
    estimates = c.link_estimates()
    assert {est.link_id for est in estimates} == {"lte", "lora"}


def test_missing_comms_section_is_empty() -> None:
    c = CommsSubsystem({})
    assert c.link_ids == []
    label, reason = c.derive_state()
    assert label is CommsState.DENIED
    assert "no links" in reason.lower()


def test_bad_link_entries_skipped() -> None:
    profile: Mapping[str, Any] = {
        "comms": {
            "links": [
                {"id": "good", "bandwidth_bps": 1000, "max_age_s": 30},
                {"bandwidth_bps": 1000},  # missing id
                "not a mapping",
                {"id": "bad-numbers", "bandwidth_bps": "nope"},
            ]
        }
    }
    c = CommsSubsystem(profile)
    assert c.link_ids == ["good"]


def test_sensor_obs_payload_includes_per_link_state() -> None:
    c = CommsSubsystem(_profile())
    obs = c.sensor_obs()
    assert obs.source == "comms"
    assert len(obs.payload["links"]) == 2
    for link in obs.payload["links"]:
        assert {
            "link_id", "rssi_dbm", "loss_pct", "throughput_bps", "capacity_bps", "connected"
        } <= set(link)


# -- BL-048 / ADR 0053: propagation-aware link quality --------------------


def _prop_link() -> Mapping[str, Any]:
    return {
        "id": "relay",
        "bandwidth_bps": 2_000_000,
        "rssi_dbm_nominal": -80,
        "loss_pct_nominal": 0.5,
        "max_age_s": 600.0,
        "propagation": {
            "peer": {"lat": 47.0, "lon": 12.98, "alt_m": 520},
            "tx_power_dbm": 20.0,
            "frequency_hz": 2.4e9,
            "excess_loss_db": 5.0,
            "noise_floor_dbm": -100.0,
            "snr_floor_db": 5.0,
            "snr_full_db": 20.0,
            "good_rssi_dbm": -85.0,
            "sensitivity_dbm": -115.0,
            "loss_floor_pct": 0.5,
        },
    }


def _prop_subsystem(pos: dict[str, float]) -> CommsSubsystem:
    return CommsSubsystem(
        {"comms": {"links": [_prop_link()]}},
        position_fn=lambda: (pos["lat"], pos["lon"], pos["alt"]),
    )


def test_propagation_link_solves_quality_from_geometry() -> None:
    pos = {"lat": 47.0, "lon": 13.0, "alt": 500.0}
    c = _prop_subsystem(pos)
    c.step(1.0)
    near = c.link("relay")
    assert near is not None
    assert near.range_m is not None and near.range_m > 0.0
    assert near.path_loss_db is not None and near.snr_db is not None
    assert near.loss_pct < 5.0
    assert near.capacity_bps > 0.25 * near.bandwidth_bps
    # Capture scalars: c.link() returns the same object, mutated in place by step.
    near_rssi, near_cap, near_loss = near.rssi_dbm, near.capacity_bps, near.loss_pct

    pos["lon"] = 13.30
    c.step(1.0)
    far = c.link("relay")
    assert far is not None
    assert far.rssi_dbm < near_rssi
    assert far.capacity_bps < near_cap
    assert far.loss_pct > near_loss


def test_static_link_capacity_equals_bandwidth() -> None:
    c = CommsSubsystem(_profile())
    lte = c.link("lte")
    assert lte is not None
    assert lte.propagation is None
    assert lte.capacity_bps == pytest.approx(lte.bandwidth_bps)
    # Stepping does not touch a static link's capacity (the coupling is inert).
    c.step(1.0)
    assert lte.capacity_bps == pytest.approx(lte.bandwidth_bps)


def test_propagation_recompute_skipped_when_link_forced() -> None:
    pos = {"lat": 47.0, "lon": 13.0, "alt": 500.0}
    c = _prop_subsystem(pos)
    c.set_link_state("relay", connected=False)
    pos["lon"] = 13.30
    c.step(1.0)
    relay = c.link("relay")
    assert relay is not None
    # A forced link keeps its override; the budget was not solved for it.
    assert relay.range_m is None
    assert relay.rssi_dbm == pytest.approx(-80.0)


def test_tx_caps_throughput_at_solved_capacity() -> None:
    pos = {"lat": 47.0, "lon": 13.20, "alt": 500.0}
    c = _prop_subsystem(pos)
    c.step(1.0)
    relay = c.link("relay")
    assert relay is not None
    assert relay.capacity_bps < relay.bandwidth_bps  # a poor channel lowered the ceiling
    c.tx("relay", 10_000_000)  # a huge packet on the first send
    assert relay.throughput_bps == pytest.approx(relay.capacity_bps)


def test_derive_degraded_when_capacity_collapses() -> None:
    pos = {"lat": 47.0, "lon": 13.30, "alt": 500.0}
    c = _prop_subsystem(pos)
    c.step(1.0)
    relay = c.link("relay")
    assert relay is not None
    assert relay.is_live() is True  # still within max_age, so carrier present
    assert relay.capacity_bps <= 0.25 * relay.bandwidth_bps
    label, _ = c.derive_state()
    assert label is CommsState.DEGRADED
