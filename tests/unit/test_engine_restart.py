"""Engine restart-after-stop and FSM context surfacing.

Closes D-05: ``Engine.tick()`` after ``stop()`` used to call
``StateMachine.transition('boot')`` from SHUTDOWN, which raised. The
engine now traverses ``SHUTDOWN -> STOWED -> BOOT`` on a second
``start()`` call.

Also pins the SC-2 path: ``request_transition('mission', ...)`` consults
engine-derived thermal headroom plus any caller-supplied overrides.
"""

from __future__ import annotations

from nous.engine import Engine
from nous.state.machine import Mode


def test_engine_restartable_after_stop(engine: Engine) -> None:
    assert engine.state.mode is Mode.IDLE
    engine.stop()
    after_stop = engine.fsm.current
    assert after_stop is Mode.SHUTDOWN
    engine.start()
    after_restart = engine.fsm.current
    assert after_restart is Mode.IDLE
    # And one more tick must not raise.
    engine.tick()


def test_request_transition_refuses_mission_without_headroom(engine: Engine) -> None:
    # Force IDLE so the FSM is positioned at the mission decision point.
    engine.fsm.reset(Mode.IDLE)
    engine.state.mode = Mode.IDLE
    ok, _mode, reason = engine.request_transition(
        "mission",
        context={"thermal_headroom_c": 1.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert not ok
    assert "below threshold" in reason


def test_request_transition_admits_mission_with_headroom(engine: Engine) -> None:
    engine.fsm.reset(Mode.IDLE)
    engine.state.mode = Mode.IDLE
    ok, mode, _reason = engine.request_transition(
        "mission",
        context={"thermal_headroom_c": 15.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert ok
    assert mode is Mode.MISSION


def test_request_transition_unknown_trigger_does_not_raise(engine: Engine) -> None:
    engine.fsm.reset(Mode.IDLE)
    engine.state.mode = Mode.IDLE
    ok, _mode, reason = engine.request_transition("flying_unicorn")
    assert not ok
    assert "no transition" in reason
