"""EMCON emission-control postures and the comms tx gate (BL-060 / ADR 0065)."""

from __future__ import annotations

from typing import Any

import numpy as np

from nous.state.emcon import SILENT, UNRESTRICTED, Emcon
from nous.subsystems.comms import CommsSubsystem

_PROFILE: dict[str, Any] = {
    "name": "t",
    "comms": {
        "links": [
            {
                "id": "wifi",
                "bandwidth_bps": 1_000_000,
                "rssi_dbm_nominal": -55,
                "loss_pct_nominal": 0.1,
                "max_age_s": 30,
            },
            {
                "id": "lte",
                "bandwidth_bps": 1_000_000,
                "rssi_dbm_nominal": -75,
                "loss_pct_nominal": 0.5,
                "max_age_s": 30,
            },
        ],
        "emcon": {
            "default": "unrestricted",
            "profiles": {"low_pi": {"permit_links": ["lte"]}},
        },
    },
}


def test_unrestricted_by_default_permits_all_links() -> None:
    emcon = Emcon({"links": [{"id": "wifi"}, {"id": "lte"}]})
    assert emcon.active == UNRESTRICTED
    assert emcon.permits("wifi") and emcon.permits("lte")
    assert emcon.configured is False


def test_silent_blocks_all_links() -> None:
    emcon = Emcon({"links": [{"id": "wifi"}, {"id": "lte"}]})
    assert emcon.set_profile(SILENT) is True
    assert not emcon.permits("wifi")
    assert not emcon.permits("lte")


def test_named_profile_permits_a_subset() -> None:
    emcon = Emcon(_PROFILE["comms"])
    assert emcon.configured is True
    assert emcon.set_profile("low_pi") is True
    assert emcon.permits("lte") is True
    assert emcon.permits("wifi") is False


def test_unknown_profile_is_rejected() -> None:
    emcon = Emcon(_PROFILE["comms"])
    assert emcon.set_profile("nope") is False
    assert emcon.active == UNRESTRICTED


def test_tx_is_gated_by_the_active_profile() -> None:
    comms = CommsSubsystem(_PROFILE, rng=np.random.default_rng(0))
    assert comms.tx("wifi", 100) == 100  # unrestricted: accepted
    assert comms.emcon.set_profile(SILENT) is True
    assert comms.tx("wifi", 100) == 0  # silent: blocked
    assert comms.emcon.set_profile("low_pi") is True
    assert comms.tx("wifi", 100) == 0  # not permitted under low_pi
    assert comms.tx("lte", 100) == 100  # permitted


def test_unconfigured_links_in_a_profile_are_dropped() -> None:
    cfg: dict[str, Any] = {
        "links": [{"id": "wifi"}, {"id": "lte"}],
        "emcon": {"profiles": {"typo": {"permit_links": ["wifi", "satcom"]}}},
    }
    emcon = Emcon(cfg)
    assert emcon.set_profile("typo") is True
    assert emcon.permits("wifi") is True
    assert emcon.permits("satcom") is False
    assert emcon.status()["permitted_links"] == ["wifi"]


def test_set_profile_strips_surrounding_whitespace() -> None:
    emcon = Emcon(_PROFILE["comms"])
    assert emcon.set_profile("  low_pi  ") is True
    assert emcon.active == "low_pi"


def _windowed(window: dict[str, Any]) -> Emcon:
    return Emcon(
        {
            "links": [{"id": "lte"}],
            "emcon": {"profiles": {"burst": {"permit_links": ["lte"], "window": window}}},
        }
    )


def test_duty_cycle_window_gates_emission_by_time() -> None:
    emcon = _windowed({"period_s": 60, "on_s": 5})
    assert emcon.set_profile("burst") is True
    assert emcon.permits("lte", now_s=0.0) is True
    assert emcon.permits("lte", now_s=4.9) is True
    assert emcon.permits("lte", now_s=5.0) is False
    assert emcon.permits("lte", now_s=59.0) is False
    assert emcon.permits("lte", now_s=60.0) is True  # next burst
    assert emcon.permits("lte") is True  # no clock: membership-only fallback


def test_window_phase_offset_shifts_the_burst() -> None:
    emcon = _windowed({"period_s": 60, "on_s": 5, "phase_s": 10})
    emcon.set_profile("burst")
    assert emcon.permits("lte", now_s=9.0) is False
    assert emcon.permits("lte", now_s=10.0) is True
    assert emcon.permits("lte", now_s=14.9) is True
    assert emcon.permits("lte", now_s=15.0) is False


def test_malformed_or_always_open_window_is_ignored() -> None:
    always = _windowed({"period_s": 5, "on_s": 5})  # on >= period: no schedule
    always.set_profile("burst")
    assert always.permits("lte", now_s=3.0) is True
    assert always.status(now_s=3.0)["window"] is None
    bad = _windowed({"period_s": 0, "on_s": 1})  # non-positive period: ignored
    bad.set_profile("burst")
    assert bad.permits("lte", now_s=99.0) is True


def test_status_reports_window_and_emitting() -> None:
    emcon = _windowed({"period_s": 60, "on_s": 5})
    emcon.set_profile("burst")
    open_status = emcon.status(now_s=1.0)
    assert open_status["emitting"] is True
    assert open_status["window"] == {"period_s": 60.0, "on_s": 5.0, "phase_s": 0.0}
    assert emcon.status(now_s=30.0)["emitting"] is False
