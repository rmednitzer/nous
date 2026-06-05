"""Hand-rolled finite-state machine for the simulator's mission posture.

The transition table is explicit (a ``dict[tuple[Mode, str], Mode]``) so the
allowed transitions are reviewable in a single screen and an unknown
trigger is a hard error rather than a silent no-op. See ADR-0004 for why
the project rolls its own FSM instead of pulling in ``transitions`` or
``automat``.

A transition into an operational mode is safety-gated. ``_SAFETY_GATES``
maps such a transition to the STPA constraints it must satisfy (SC-2
thermal headroom, SC-8 power reserve); each gate names the context key the
constraint judges. The machine routes every gate through a
:class:`~nous.safety.SafetyEnforcer` (ADR 0022), so a refused gate raises
``GuardDenied`` carrying the enforcer's structured reason and the enforcer
records the violation for ``device_info`` to surface. A gate whose context
is missing fails closed, preserving the UCAs in
``docs/stpa/07-unsafe-control-actions.md``.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, NamedTuple

from ..safety import SafetyEnforcer, SafetyResult, floor_threshold

__all__ = [
    "SC_POWER_RESERVE",
    "SC_THERMAL_HEADROOM",
    "GuardDenied",
    "Mode",
    "StateMachine",
    "build_fsm_enforcer",
    "register_fsm_constraints",
]


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


SC_THERMAL_HEADROOM = "SC-2"
SC_POWER_RESERVE = "SC-8"


class _SafetyGate(NamedTuple):
    """One constraint a transition must satisfy, and the context key it judges."""

    constraint_id: str
    candidate_key: str


_GATE_THERMAL = _SafetyGate(SC_THERMAL_HEADROOM, "thermal_headroom_c")
_GATE_POWER = _SafetyGate(SC_POWER_RESERVE, "soc_pct")

# Entering an operational mode (MISSION / RELAY / MONITORING / C2, and the
# recover/cool paths back into them) requires both thermal headroom (SC-2)
# and battery reserve (SC-8). Gates are checked in order, so the first
# unsatisfied constraint is the one the refusal names.
_SAFETY_GATES: dict[tuple[Mode, str], tuple[_SafetyGate, ...]] = {
    (Mode.IDLE, "mission"): (_GATE_THERMAL, _GATE_POWER),
    (Mode.IDLE, "relay"): (_GATE_THERMAL, _GATE_POWER),
    (Mode.IDLE, "monitoring"): (_GATE_THERMAL, _GATE_POWER),
    (Mode.IDLE, "c2"): (_GATE_THERMAL, _GATE_POWER),
    (Mode.DEGRADED, "recover"): (_GATE_THERMAL, _GATE_POWER),
    (Mode.THERMAL_LIMIT, "cool"): (_GATE_THERMAL, _GATE_POWER),
    (Mode.LOW_POWER, "recover"): (_GATE_THERMAL, _GATE_POWER),
}


def register_fsm_constraints(enforcer: SafetyEnforcer) -> None:
    """Register the FSM's safety-gate evaluators on ``enforcer``.

    SC-2 floors thermal headroom at the profile threshold; SC-8 floors
    state-of-charge at the profile's critical reserve. Both fail closed on
    missing, non-numeric, or non-finite context (ADR 0018, ADR 0022).
    """
    enforcer.register(
        SC_THERMAL_HEADROOM,
        floor_threshold(
            "thermal_headroom_threshold_c", label="thermal headroom", unit="C"
        ),
    )
    enforcer.register(
        SC_POWER_RESERVE,
        floor_threshold("soc_pct_critical", label="SoC", unit="%"),
    )


def build_fsm_enforcer() -> SafetyEnforcer:
    """A :class:`~nous.safety.SafetyEnforcer` with the FSM safety gates registered."""
    enforcer = SafetyEnforcer()
    register_fsm_constraints(enforcer)
    return enforcer


class StateMachine:
    """Explicit-table FSM over :class:`Mode` with enforcer-routed safety gates.

    ``checker`` is the :class:`~nous.safety.SafetyEnforcer` the safety gates
    evaluate through. The engine injects its shared enforcer so the violation
    counters surface through ``device_info``; a bare machine builds its own so
    it stays self-protecting (and fail-closed) when used without the engine.
    """

    def __init__(
        self, start: Mode = Mode.STOWED, *, checker: SafetyEnforcer | None = None
    ) -> None:
        self._current = start
        self._checker = checker if checker is not None else build_fsm_enforcer()
        self._history: list[tuple[Mode, str, Mode]] = []
        self._refusals: list[tuple[Mode, str, Mode, str]] = []
        self._last_checks: list[SafetyResult] = []

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
        :class:`GuardDenied` when a safety gate refuses the transition. Each
        gate is evaluated through the injected
        :class:`~nous.safety.SafetyEnforcer`; the results of the most recent
        attempt are available via :meth:`last_safety_checks` for the audit
        trail.
        """
        self._last_checks = []
        key = (self._current, trigger)
        if key not in _TRANSITIONS:
            raise ValueError(
                f"no transition from {self._current.value!r} on trigger {trigger!r}"
            )
        nxt = _TRANSITIONS[key]
        ctx = context or {}
        for gate in _SAFETY_GATES.get(key, ()):
            result = self._checker.check(
                gate.constraint_id, ctx.get(gate.candidate_key), evidence=ctx
            )
            self._last_checks.append(result)
            if not result.approved:
                self._refusals.append((self._current, trigger, nxt, result.reason))
                raise GuardDenied(self._current, trigger, nxt, result.reason)
        self._history.append((self._current, trigger, nxt))
        self._current = nxt
        return nxt

    def history(self) -> list[tuple[Mode, str, Mode]]:
        return list(self._history)

    def refusals(self) -> list[tuple[Mode, str, Mode, str]]:
        """Return guard-refused transitions for the audit log."""
        return list(self._refusals)

    def last_safety_checks(self) -> list[SafetyResult]:
        """SafetyResults from the most recent ``transition`` attempt.

        Empty for an ungated transition or one that raised ``ValueError``
        before reaching the gate loop. The engine mirrors these to the audit
        log under ``Tier.SAFETY`` (ADR 0022).
        """
        return list(self._last_checks)

    def reset(self, mode: Mode = Mode.STOWED) -> None:
        """Force the FSM back to ``mode`` without traversing transitions.

        Used by the engine to restart cleanly after ``stop()`` without
        threading a ``reset`` trigger through SHUTDOWN -> STOWED.
        """
        self._current = mode
