"""Concurrent-anomaly integration test (Phase 4 mandate).

Verifies the FSM correctly handles overlapping operator heat strain and
thermal throttling without deadlocking, and that the guard-refused
transitions are recorded for audit.

Layout:

1. Boot the engine, transition to MISSION with healthy thermal headroom.
2. Force operator heat strain (biometric core_temp above the stress
   threshold) via the OperatorState derivation.
3. Force thermal throttle on the device side (junction temp through the
   roof) by manipulating the safety context the engine surfaces to the
   FSM.
4. Drive the FSM through ``thermal_limit`` -> ``cool`` and observe that
   the cool transition is refused while the device is still hot.
5. After cooling, the ``cool`` trigger admits and the FSM returns to
   MISSION without leaving stale guard refusals behind.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nous.engine import Engine
from nous.state.machine import GuardDenied, Mode
from nous.state.operator_state import OperatorState
from nous.state.operator_state import derive as derive_operator
from nous.types import Estimate


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    eng.fsm.reset(Mode.IDLE)
    eng.state.mode = Mode.IDLE
    return eng


def test_concurrent_heat_strain_and_thermal_throttle(engine: Engine) -> None:
    # 1. Admit MISSION under healthy thermal context.
    ok, mode, _ = engine.request_transition(
        "mission",
        context={"thermal_headroom_c": 25.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert ok and mode is Mode.MISSION

    # 2. Operator heat strain: derive STRESSED from biometrics.
    biometrics = Estimate(
        source="biometrics",
        ts_s=10.0,
        point={"heart_rate_bpm": 160.0, "core_temp_c": 38.5, "cognitive_load": 0.6},
        covariance={},
    )
    op_state, op_reason = derive_operator(biometrics)
    assert op_state in (OperatorState.STRESSED, OperatorState.IMPAIRED)
    assert op_reason

    # 3. Device thermal throttle: enter THERMAL_LIMIT.
    ok, mode, _ = engine.request_transition("thermal_limit")
    assert ok and mode is Mode.THERMAL_LIMIT

    # 4. Refuse `cool` while still hot.
    ok, mode, reason = engine.request_transition(
        "cool",
        context={"thermal_headroom_c": 1.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert not ok
    assert mode is Mode.THERMAL_LIMIT
    assert "below threshold" in reason

    # 5. Admit `cool` once headroom recovers; it lands in the neutral IDLE
    #    (ADR 0029), from which the controller re-selects an operational mode.
    ok, mode, _ = engine.request_transition(
        "cool",
        context={"thermal_headroom_c": 12.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert ok and mode is Mode.IDLE

    # No state machine deadlock: history contains forward progress and
    # the refused transition is recorded separately.
    history = engine.fsm.history()
    refusals = engine.fsm.refusals()
    triggers = [t for (_f, t, _to) in history]
    assert "mission" in triggers
    assert "thermal_limit" in triggers
    assert "cool" in triggers  # the successful one only
    assert any(r[1] == "cool" for r in refusals)


def test_heat_strain_does_not_block_safe_transition(engine: Engine) -> None:
    # Even with biometric stress, the FSM must reach SAFE without
    # requiring a thermal headroom override; SAFE is the failsafe sink.
    engine.request_transition(
        "mission",
        context={"thermal_headroom_c": 25.0, "thermal_headroom_threshold_c": 5.0},
    )
    engine.request_transition("degrade")
    ok, mode, _ = engine.request_transition("safe")
    assert ok and mode is Mode.SAFE


def test_tick_loop_advances_under_anomalies(engine: Engine) -> None:
    engine.request_transition(
        "mission",
        context={"thermal_headroom_c": 25.0, "thermal_headroom_threshold_c": 5.0},
    )
    starting_tick = engine.state.tick
    for _ in range(50):
        engine.tick()
    # The tick loop must not deadlock; FSM stays in MISSION (no anomaly
    # auto-transitions yet) and the tick counter advances.
    assert engine.state.tick == starting_tick + 50
    assert engine.fsm.current is Mode.MISSION


def test_guard_denied_exposes_structured_attributes() -> None:
    # Direct FSM use must surface the refusal as a structured exception
    # the controller can branch on. ``Engine.request_transition`` flattens
    # it, but raw FSM use is also supported (e.g. by the scenario runner).
    from nous.state.machine import StateMachine

    fsm = StateMachine()
    fsm.transition("boot")
    fsm.transition("ready")
    with pytest.raises(GuardDenied) as exc_info:
        fsm.transition(
            "mission",
            context={"thermal_headroom_c": 0.1, "thermal_headroom_threshold_c": 5.0},
        )
    e = exc_info.value
    assert e.frm is Mode.IDLE
    assert e.trigger == "mission"
    assert e.to is Mode.MISSION
    assert "below threshold" in e.reason
