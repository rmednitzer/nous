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


def test_silent_profile_reports_not_emitting() -> None:
    emcon = Emcon({"links": [{"id": "wifi"}, {"id": "lte"}]})
    emcon.set_profile(SILENT)
    status = emcon.status(now_s=0.0)
    assert status["emitting"] is False
    assert status["permitted_links"] == []


def test_non_finite_window_values_are_ignored() -> None:
    # A NaN phase must not register an always-closed window: it falls back to
    # no offset rather than silently black-holing the profile's traffic.
    nan_phase = _windowed({"period_s": 60, "on_s": 5, "phase_s": float("nan")})
    nan_phase.set_profile("burst")
    assert nan_phase.permits("lte", now_s=0.0) is True
    # A non-finite period is malformed and dropped, leaving the profile unwindowed.
    inf_period = _windowed({"period_s": float("inf"), "on_s": 5})
    inf_period.set_profile("burst")
    assert inf_period.status(now_s=0.0)["window"] is None
    assert inf_period.permits("lte", now_s=999.0) is True


def _minimizing(policy: dict[str, Any]) -> Emcon:
    return Emcon(
        {
            "links": [{"id": "lte"}],
            "emcon": {"profiles": {"min": {"permit_links": ["lte"], "minimize": policy}}},
        }
    )


def test_minimize_coarsens_position_fields() -> None:
    emcon = _minimizing({"position_decimals": 2})
    emcon.set_profile("min")
    out = emcon.minimize({"uid": "x", "lat": 47.123456, "lon": 13.654321})
    assert out["lat"] == 47.12
    assert out["lon"] == 13.65
    assert out["uid"] == "x"


def test_minimize_drops_named_fields() -> None:
    emcon = _minimizing({"drop": ["heart_rate_bpm", "uid"]})
    emcon.set_profile("min")
    out = emcon.minimize({"uid": "x", "heart_rate_bpm": 70, "lat": 47.0})
    assert "uid" not in out
    assert "heart_rate_bpm" not in out
    assert out["lat"] == 47.0


def test_minimize_is_identity_without_a_policy() -> None:
    emcon = Emcon({"links": [{"id": "lte"}]})  # unrestricted, no policy
    data = {"lat": 47.123456, "uid": "x"}
    out = emcon.minimize(data)
    assert out == data
    assert out is not data  # a defensive copy, not the original mapping


def test_minimize_status_reports_the_active_policy() -> None:
    emcon = _minimizing({"position_decimals": 1, "drop": ["uid"]})
    emcon.set_profile("min")
    status = emcon.status()
    assert status["minimize"] == {"position_decimals": 1, "drop": ["uid"]}
    assert "min" in status["minimizers"]


def test_minimize_coarsens_altitude_fields() -> None:
    emcon = _minimizing({"position_decimals": 1})
    emcon.set_profile("min")
    out = emcon.minimize({"lat": 47.126, "hae": 612.347, "alt_m": 612.347})
    assert out["lat"] == 47.1
    assert out["hae"] == 612.3
    assert out["alt_m"] == 612.3


def test_builtin_postures_cannot_be_overridden_by_config() -> None:
    # A config profile named like a built-in must not weaken radio silence.
    emcon = Emcon(
        {
            "links": [{"id": "wifi"}, {"id": "lte"}],
            "emcon": {"profiles": {"silent": {"permit_links": ["wifi", "lte"]}}},
        }
    )
    assert emcon.set_profile(SILENT) is True
    assert emcon.permits("wifi") is False
    assert emcon.permits("lte") is False
    assert emcon.status()["profiles"]["silent"] == []


def test_extreme_phase_s_is_normalised_modulo_period() -> None:
    # A phase beyond one period wraps, so a huge value cannot black-hole traffic.
    emcon = _windowed({"period_s": 60, "on_s": 5, "phase_s": 65})  # 65 == 5 mod 60
    emcon.set_profile("burst")
    assert emcon.permits("lte", now_s=7.0) is True  # open over [5, 10)
    assert emcon.permits("lte", now_s=3.0) is False
    huge = _windowed({"period_s": 60, "on_s": 5, "phase_s": 1e18})
    huge.set_profile("burst")
    # Not permanently closed: some instant within a period is still open.
    assert any(huge.permits("lte", now_s=float(t)) for t in range(60))
