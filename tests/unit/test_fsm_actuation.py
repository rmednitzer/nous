"""FSM actuation, neutral recovery, and fail-closed robustness (ADR 0029).

The companion to ``test_fsm_auto_safe.py``. Those tests pin which mode the
auto-safe selects; these pin what entering that mode *does*: the headline
gap the review found was that the FSM mode was observational, so auto-safing
relabelled the posture without shedding any load. Here the entry actions
actuate (LOW_POWER / SAFE / THERMAL_LIMIT cap delivered compute load, draw
falls, the pack drains slower, recovery lifts the cap), recovery lands in the
neutral IDLE, a malformed safety threshold fails closed instead of crashing
the tick loop, IDLE can reach the failsafe states, and the in-memory history
is bounded.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from nous.engine import (
    _OPERATOR_PERSISTENCE_TICKS,
    Engine,
    ProfileModel,
)
from nous.state.comms_state import CommsState
from nous.state.machine import _HISTORY_MAXLEN, Mode, StateMachine
from nous.state.operator_state import OperatorState

_OK_ENTRY = {
    "thermal_headroom_c": 30.0,
    "thermal_headroom_threshold_c": 5.0,
    "soc_pct": 80.0,
    "soc_pct_critical": 5.0,
}


def _engine_in(mode_trigger: str) -> Engine:
    """Boot an engine and drive it to the operational mode under test."""
    eng = Engine()
    eng.start()
    eng.request_transition("ready")
    ok, _mode, _reason = eng.request_transition(mode_trigger, context=_OK_ENTRY)
    assert ok
    return eng


def _drive_operator_incapacitated(eng: Engine) -> None:
    """Hold the operator label INCAPACITATED past the debounce window."""
    eng.state.operator_state = OperatorState.INCAPACITATED
    for _ in range(_OPERATOR_PERSISTENCE_TICKS):
        eng._auto_safe()


# --- Actuation: entering a safed posture sheds compute load ----------------


def test_low_power_entry_sheds_load_and_cuts_draw(tmp_nous_home: Path) -> None:
    # The headline finding: entering LOW_POWER must actually shed load, not
    # only relabel the posture. The controller's request is preserved so the
    # cap can lift on recovery.
    eng = _engine_in("mission")
    eng.compute.set_load_pct(100.0)
    draw_full = eng.compute.draw_w
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.state.mode is Mode.LOW_POWER
    assert eng.compute.load_pct == pytest.approx(15.0)
    assert eng.compute.requested_load_pct == pytest.approx(100.0)
    assert eng.compute.draw_w < draw_full


def test_thermal_limit_entry_caps_to_cooldown_load(tmp_nous_home: Path) -> None:
    eng = _engine_in("mission")
    eng.compute.set_load_pct(100.0)
    eng.thermal.set_junction_c(84.0)  # ~1C headroom, below the 5C threshold
    eng._auto_safe()
    assert eng.state.mode is Mode.THERMAL_LIMIT
    assert eng.compute.load_pct == pytest.approx(40.0)


def test_safe_entry_caps_to_minimum_load(tmp_nous_home: Path) -> None:
    eng = _engine_in("mission")
    eng.compute.set_load_pct(100.0)
    _drive_operator_incapacitated(eng)
    assert eng.state.mode is Mode.SAFE
    assert eng.compute.load_pct == pytest.approx(5.0)


def test_degraded_keeps_full_load(tmp_nous_home: Path) -> None:
    # DEGRADED is the generic / comms posture, not a power or thermal command,
    # so it does not cap load.
    eng = _engine_in("relay")
    eng.compute.set_load_pct(100.0)
    eng.state.comms_state = CommsState.DENIED
    eng._auto_safe()
    assert eng.state.mode is Mode.DEGRADED
    assert eng.compute.load_pct == pytest.approx(100.0)


def test_recover_to_idle_lifts_the_load_ceiling(tmp_nous_home: Path) -> None:
    eng = _engine_in("mission")
    eng.compute.set_load_pct(100.0)
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.compute.load_pct == pytest.approx(15.0)
    eng.power.set_soc_pct(80.0)
    ok, mode, _reason = eng.request_transition("recover")
    assert ok
    assert mode is Mode.IDLE
    assert eng.compute.load_pct == pytest.approx(100.0)


def test_low_power_slows_pack_drain(tmp_nous_home: Path) -> None:
    # The "sustains" half of H-2/H-8: the shed load means the pack drains
    # slower. Two engines at full load, one safed to LOW_POWER, the pack
    # equalised so the only difference is the delivered load.
    full = _engine_in("mission")
    shed = _engine_in("mission")
    for eng in (full, shed):
        eng.compute.set_load_pct(100.0)
    shed.power.set_soc_pct(2.0)
    shed.tick()
    assert shed.state.mode is Mode.LOW_POWER
    full.power.set_soc_pct(50.0)
    shed.power.set_soc_pct(50.0)
    full_before = full.power.soc_pct
    shed_before = shed.power.soc_pct
    full.tick()
    shed.tick()
    assert (shed_before - shed.power.soc_pct) < (full_before - full.power.soc_pct)


def test_load_ceiling_survives_profile_reload(tmp_nous_home: Path) -> None:
    # A hot reload rebuilds the compute subsystem (and resets the controller's
    # requested load to the profile default); the active posture's entry action
    # is re-applied so the LOW_POWER cap is not silently dropped.
    eng = _engine_in("mission")
    eng.compute.set_load_pct(100.0)
    eng.power.set_soc_pct(2.0)
    eng._auto_safe()
    assert eng.state.mode is Mode.LOW_POWER
    eng.reload_profile()
    assert eng.state.mode is Mode.LOW_POWER
    assert eng.compute.truth()["mode_load_ceiling_pct"] == pytest.approx(15.0)


# --- Fail closed on a malformed profile ------------------------------------


def test_profile_model_rejects_non_numeric_reserve() -> None:
    with pytest.raises(ValidationError):
        ProfileModel.model_validate(
            {"name": "x", "power": {"soc_pct_critical_threshold": "oops"}}
        )


def test_profile_model_rejects_non_numeric_headroom() -> None:
    with pytest.raises(ValidationError):
        ProfileModel.model_validate(
            {"name": "x", "thermal": {"headroom_threshold_c": "warm"}}
        )


def test_profile_model_accepts_floatable_threshold() -> None:
    # A YAML numeric string is acceptable; the gate coerces with float().
    ProfileModel.model_validate(
        {"name": "x", "power": {"soc_pct_critical_threshold": "5"}}
    )


def test_malformed_reserve_refuses_operational_entry(tmp_nous_home: Path) -> None:
    # Defence in depth: a directly-built profile bypasses the load-time
    # validation, so the context build omits the bad reserve and SC-8 fails
    # closed rather than admitting the entry.
    eng = Engine()
    eng.start()
    eng.request_transition("ready")
    bad_power = {**dict(eng.profile["power"]), "soc_pct_critical_threshold": "oops"}
    eng.profile = {**dict(eng.profile), "power": bad_power}
    assert "soc_pct_critical" not in eng._safety_context()
    ok, mode, reason = eng.request_transition("mission")
    assert not ok
    assert mode is Mode.IDLE
    assert "SC-8" in reason


def test_tick_survives_malformed_reserve_and_safes(tmp_nous_home: Path) -> None:
    # The original M3 crash: a non-numeric reserve made the tick loop do
    # float("oops"). Now the tick completes and the FSM auto-safes instead.
    eng = _engine_in("mission")
    bad_power = {**dict(eng.profile["power"]), "soc_pct_critical_threshold": "oops"}
    eng.profile = {**dict(eng.profile), "power": bad_power}
    eng.tick()
    assert eng.state.mode is Mode.LOW_POWER


# --- Failsafe from IDLE, deepening, and bounded history --------------------


def test_idle_reaches_safe_and_fault_ungated() -> None:
    assert StateMachine(Mode.IDLE).transition("safe") is Mode.SAFE
    assert StateMachine(Mode.IDLE).transition("fault") is Mode.FAULT


def test_operator_deepens_impaired_posture_to_safe(tmp_nous_home: Path) -> None:
    # A confirmed-incapacitated operator deepens an already-impaired posture
    # (here DEGRADED, reached via a dead link) to the full SAFE.
    eng = _engine_in("relay")
    eng.state.comms_state = CommsState.DENIED
    eng._auto_safe()
    assert eng.state.mode is Mode.DEGRADED
    eng.state.comms_state = CommsState.CONNECTED
    _drive_operator_incapacitated(eng)
    assert eng.state.mode is Mode.SAFE
    assert eng.compute.load_pct == pytest.approx(5.0)


def test_in_memory_history_is_bounded() -> None:
    fsm = StateMachine(Mode.IDLE)
    for _ in range(_HISTORY_MAXLEN + 25):
        fsm.transition("safe")  # IDLE -> SAFE (ungated)
        fsm.transition("recover")  # SAFE -> IDLE (ungated)
    assert len(fsm.history()) == _HISTORY_MAXLEN
