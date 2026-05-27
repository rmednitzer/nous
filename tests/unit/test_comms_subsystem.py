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


def test_tx_resets_age_and_marks_live() -> None:
    c = CommsSubsystem(_profile())
    c.step(31.0)
    accepted = c.tx("lte", 1000)
    assert accepted == 1000
    lte = c.link("lte")
    assert lte is not None
    assert lte.is_live() is True
    assert lte.age_s == pytest.approx(0.0)


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
        assert {"link_id", "rssi_dbm", "loss_pct", "throughput_bps", "connected"} <= set(
            link
        )
