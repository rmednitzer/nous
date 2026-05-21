"""Hand-rolled finite-state machine for the simulator's mission posture.

The transition table is explicit (a ``dict[tuple[Mode, str], Mode]``) so the
allowed transitions are reviewable in a single screen and an unknown
trigger is a hard error rather than a silent no-op. See ADR-0004 for why
the project rolls its own FSM instead of pulling in ``transitions`` or
``automat``.

Transitions can carry a precondition guard. Guards take the proposed
``(from_mode, to_mode)`` pair plus a context mapping supplied by the
controller and return ``(ok, reason)``. A guard that returns ``False``
turns the transition into a hard refusal (``GuardDenied``), preserving
the UCAs in ``docs/stpa/07-unsafe-control-actions.md`` -- in particular
SC-2 (no ``MISSION`` while thermal headroom is exhausted) and the
``low_power`` UCA (must fire before SoC reaches zero).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any

__all__ = ["GuardDenied", "Mode", "StateMachine"]


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


class GuardDenied(RuntimeError):
    """A transition was admitted by the table but refused by a guard."""

    def __init__(self, frm: Mode, trigger: str, to: Mode, reason: str) -> None:
        self.frm = frm
        self.trigger = trigger
        self.to = to
        self.reason = reason
        super().__init__(
            f"guard refused {frm.value!r} -{trigger!r}-> {to.value!r}: {reason}"
        )


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


Guard = Callable[[Mode, str, Mode, Mapping[str, Any]], tuple[bool, str]]


def _guard_mission_requires_thermal_headroom(
    _frm: Mode, _trigger: str, _to: Mode, ctx: Mapping[str, Any]
) -> tuple[bool, str]:
    """SC-2: refuse MISSION when thermal headroom is exhausted.

    The controller is expected to pass ``thermal_headroom_c`` and
    ``thermal_headroom_threshold_c`` in the context. Missing context is
    treated as "unknown" and the transition is refused -- a guarded FSM
    fails closed.
    """
    headroom = ctx.get("thermal_headroom_c")
    threshold = ctx.get("thermal_headroom_threshold_c")
    if headroom is None or threshold is None:
        return False, "thermal headroom unknown (SC-2 requires explicit context)"
    try:
        h = float(headroom)
        t = float(threshold)
    except (TypeError, ValueError):
        return False, "thermal headroom context is non-numeric"
    if math.isnan(h) or math.isnan(t):
        return False, "thermal headroom context is NaN"
    if h < t:
        return False, f"thermal headroom {h:.2f}C below threshold {t:.2f}C"
    return True, ""


def _guard_safe_requires_no_low_power_blockers(
    _frm: Mode, _trigger: str, _to: Mode, ctx: Mapping[str, Any]
) -> tuple[bool, str]:
    """UCA: ``trigger=low_power`` issued too late (after SoC=0).

    If the controller is asking to leave LOW_POWER via ``recover`` while
    SoC is still under the critical threshold, refuse. Acts as a guardrail
    on top of SC-2's spirit -- the FSM does not let the operator hand-wave
    the device back into MISSION on a dying pack.
    """
    soc = ctx.get("soc_pct")
    critical = ctx.get("soc_pct_critical")
    if soc is None or critical is None:
        return True, "no SoC context supplied; passing"
    try:
        s = float(soc)
        c = float(critical)
    except (TypeError, ValueError):
        return False, "SoC context is non-numeric"
    if math.isnan(s) or math.isnan(c):
        return False, "SoC context is NaN"
    if s < c:
        return False, f"SoC {s:.1f}% below critical {c:.1f}%"
    return True, ""


_GUARDS: dict[tuple[Mode, str], Guard] = {
    (Mode.IDLE, "mission"): _guard_mission_requires_thermal_headroom,
    (Mode.DEGRADED, "recover"): _guard_mission_requires_thermal_headroom,
    (Mode.THERMAL_LIMIT, "cool"): _guard_mission_requires_thermal_headroom,
    (Mode.LOW_POWER, "recover"): _guard_safe_requires_no_low_power_blockers,
}


class StateMachine:
    """Explicit-table FSM over :class:`Mode` with optional transition guards."""

    def __init__(self, start: Mode = Mode.STOWED) -> None:
        self._current = start
        self._history: list[tuple[Mode, str, Mode]] = []
        self._refusals: list[tuple[Mode, str, Mode, str]] = []

    @property
    def current(self) -> Mode:
        return self._current

    def can(self, trigger: str) -> bool:
        return (self._current, trigger) in _TRANSITIONS

    def would(self, trigger: str) -> Mode | None:
        """Return the destination if ``trigger`` is admitted by the table, else ``None``."""
        return _TRANSITIONS.get((self._current, trigger))

    def transition(
        self, trigger: str, *, context: Mapping[str, Any] | None = None
    ) -> Mode:
        """Move to the next state for ``trigger``.

        Raises :class:`ValueError` on an unknown table entry and
        :class:`GuardDenied` when a guard refuses the transition.
        """
        key = (self._current, trigger)
        if key not in _TRANSITIONS:
            raise ValueError(
                f"no transition from {self._current.value!r} on trigger {trigger!r}"
            )
        nxt = _TRANSITIONS[key]
        guard = _GUARDS.get(key)
        if guard is not None:
            ok, reason = guard(self._current, trigger, nxt, context or {})
            if not ok:
                self._refusals.append((self._current, trigger, nxt, reason))
                raise GuardDenied(self._current, trigger, nxt, reason)
        self._history.append((self._current, trigger, nxt))
        self._current = nxt
        return nxt

    def history(self) -> list[tuple[Mode, str, Mode]]:
        return list(self._history)

    def refusals(self) -> list[tuple[Mode, str, Mode, str]]:
        """Return guard-refused transitions for the audit log."""
        return list(self._refusals)

    def reset(self, mode: Mode = Mode.STOWED) -> None:
        """Force the FSM back to ``mode`` without traversing transitions.

        Used by the engine to restart cleanly after ``stop()`` without
        threading a ``reset`` trigger through SHUTDOWN -> STOWED.
        """
        self._current = mode
