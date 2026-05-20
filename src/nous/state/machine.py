"""Hand-rolled finite-state machine for the simulator's mission posture.

The transition table is explicit (a ``dict[tuple[Mode, str], Mode]``) so the
allowed transitions are reviewable in a single screen and an unknown
trigger is a hard error rather than a silent no-op. See ADR-0004 for why
the project rolls its own FSM instead of pulling in ``transitions`` or
``automat``.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Mode", "StateMachine"]


class Mode(StrEnum):
    STOWED = "stowed"
    BOOT = "boot"
    IDLE = "idle"
    MISSION = "mission"
    RELAY = "relay"
    MONITORING = "monitoring"
    C2 = "c2"
    DEGRADED = "degraded"
    THERMAL_LIMIT = "thermal_limit"
    LOW_POWER = "low_power"
    SAFE = "safe"
    SHUTDOWN = "shutdown"
    FAULT = "fault"


_TRANSITIONS: dict[tuple[Mode, str], Mode] = {
    (Mode.STOWED, "boot"): Mode.BOOT,
    (Mode.BOOT, "ready"): Mode.IDLE,
    (Mode.BOOT, "fault"): Mode.FAULT,
    (Mode.IDLE, "mission"): Mode.MISSION,
    (Mode.IDLE, "relay"): Mode.RELAY,
    (Mode.IDLE, "monitoring"): Mode.MONITORING,
    (Mode.IDLE, "c2"): Mode.C2,
    (Mode.IDLE, "shutdown"): Mode.SHUTDOWN,
    (Mode.MISSION, "degrade"): Mode.DEGRADED,
    (Mode.MISSION, "thermal_limit"): Mode.THERMAL_LIMIT,
    (Mode.MISSION, "low_power"): Mode.LOW_POWER,
    (Mode.MISSION, "complete"): Mode.IDLE,
    (Mode.MISSION, "fault"): Mode.FAULT,
    (Mode.RELAY, "degrade"): Mode.DEGRADED,
    (Mode.RELAY, "complete"): Mode.IDLE,
    (Mode.MONITORING, "degrade"): Mode.DEGRADED,
    (Mode.MONITORING, "complete"): Mode.IDLE,
    (Mode.C2, "degrade"): Mode.DEGRADED,
    (Mode.C2, "complete"): Mode.IDLE,
    (Mode.DEGRADED, "recover"): Mode.MISSION,
    (Mode.DEGRADED, "safe"): Mode.SAFE,
    (Mode.DEGRADED, "fault"): Mode.FAULT,
    (Mode.THERMAL_LIMIT, "cool"): Mode.MISSION,
    (Mode.THERMAL_LIMIT, "safe"): Mode.SAFE,
    (Mode.LOW_POWER, "recover"): Mode.MISSION,
    (Mode.LOW_POWER, "safe"): Mode.SAFE,
    (Mode.SAFE, "recover"): Mode.IDLE,
    (Mode.SAFE, "shutdown"): Mode.SHUTDOWN,
    (Mode.BOOT, "shutdown"): Mode.SHUTDOWN,
    (Mode.MISSION, "shutdown"): Mode.SHUTDOWN,
    (Mode.RELAY, "shutdown"): Mode.SHUTDOWN,
    (Mode.MONITORING, "shutdown"): Mode.SHUTDOWN,
    (Mode.C2, "shutdown"): Mode.SHUTDOWN,
    (Mode.DEGRADED, "shutdown"): Mode.SHUTDOWN,
    (Mode.THERMAL_LIMIT, "shutdown"): Mode.SHUTDOWN,
    (Mode.LOW_POWER, "shutdown"): Mode.SHUTDOWN,
    (Mode.FAULT, "reset"): Mode.STOWED,
    (Mode.SHUTDOWN, "reset"): Mode.STOWED,
}


class StateMachine:
    """Explicit-table FSM over :class:`Mode`."""

    def __init__(self, start: Mode = Mode.STOWED) -> None:
        self._current = start
        self._history: list[tuple[Mode, str, Mode]] = []

    @property
    def current(self) -> Mode:
        return self._current

    def can(self, trigger: str) -> bool:
        return (self._current, trigger) in _TRANSITIONS

    def transition(self, trigger: str) -> Mode:
        """Move to the next state for ``trigger``; raise on an unknown transition."""
        key = (self._current, trigger)
        if key not in _TRANSITIONS:
            raise ValueError(
                f"no transition from {self._current.value!r} on trigger {trigger!r}"
            )
        nxt = _TRANSITIONS[key]
        self._history.append((self._current, trigger, nxt))
        self._current = nxt
        return nxt

    def history(self) -> list[tuple[Mode, str, Mode]]:
        return list(self._history)
