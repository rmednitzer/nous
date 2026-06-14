"""Hand-rolled finite-state machine for the simulator's mission posture.

The transition table is explicit (a ``dict[tuple[Mode, str], Mode]``) so the
allowed transitions are reviewable in a single screen and an unknown
trigger is a hard error rather than a silent no-op. See ADR-0004 for why
the project rolls its own FSM instead of pulling in ``transitions`` or
``automat``.

A transition into an operational mode is safety-gated. ``_SAFETY_GATES``
maps such a transition to the constraints it must satisfy: SC-2 thermal
headroom and SC-8 power reserve for every operational entry, an available
operator for all four, and a live comms link for the link-bearing modes
(RELAY, C2). Each gate names the context key the constraint judges, and the
entry set is the same flag set the auto-safe reads on the way out (ADR 0043).
The machine routes every gate through a
:class:`~nous.safety.SafetyEnforcer` (ADR 0022), so a refused gate raises
``GuardDenied`` carrying the enforcer's structured reason and the enforcer
records the violation for ``device_info`` to surface. A gate whose context
is missing fails closed, preserving the UCAs in
``docs/stpa/07-unsafe-control-actions.md``.

The failsafe exits are never gated and are kept complete: a ``safe`` trigger
reaches ``SAFE`` from every operational or impaired mode, and a ``fault``
trigger reaches the terminal ``FAULT`` from every powered mode (ADR 0028, ADR
0030). A hardware fault is mode-independent and unrecoverable, so it must
never be refused or stranded one rung short; it is one trigger from anywhere
the device is powered.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, NamedTuple

from ..safety import SafetyEnforcer, SafetyResult, floor_threshold, forbid_value
from .comms_state import CommsState
from .operator_state import OperatorState

__all__ = [
    "REQ_COMMS_LINK",
    "REQ_OPERATOR",
    "SC_POWER_RESERVE",
    "SC_THERMAL_HEADROOM",
    "GuardDenied",
    "Mode",
    "StateMachine",
    "build_fsm_enforcer",
    "is_impaired",
    "is_operational",
    "is_terminal",
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
    (Mode.IDLE, "safe"): Mode.SAFE,
    (Mode.IDLE, "fault"): Mode.FAULT,
    (Mode.IDLE, "shutdown"): Mode.SHUTDOWN,
    (Mode.MISSION, "degrade"): Mode.DEGRADED,
    (Mode.MISSION, "thermal_limit"): Mode.THERMAL_LIMIT,
    (Mode.MISSION, "low_power"): Mode.LOW_POWER,
    (Mode.MISSION, "complete"): Mode.IDLE,
    (Mode.MISSION, "safe"): Mode.SAFE,
    (Mode.MISSION, "fault"): Mode.FAULT,
    (Mode.RELAY, "degrade"): Mode.DEGRADED,
    (Mode.RELAY, "complete"): Mode.IDLE,
    (Mode.RELAY, "safe"): Mode.SAFE,
    (Mode.RELAY, "fault"): Mode.FAULT,
    (Mode.MONITORING, "degrade"): Mode.DEGRADED,
    (Mode.MONITORING, "complete"): Mode.IDLE,
    (Mode.MONITORING, "safe"): Mode.SAFE,
    (Mode.MONITORING, "fault"): Mode.FAULT,
    (Mode.C2, "degrade"): Mode.DEGRADED,
    (Mode.C2, "complete"): Mode.IDLE,
    (Mode.C2, "safe"): Mode.SAFE,
    (Mode.C2, "fault"): Mode.FAULT,
    (Mode.DEGRADED, "recover"): Mode.IDLE,
    (Mode.DEGRADED, "safe"): Mode.SAFE,
    (Mode.DEGRADED, "fault"): Mode.FAULT,
    (Mode.THERMAL_LIMIT, "cool"): Mode.IDLE,
    (Mode.THERMAL_LIMIT, "safe"): Mode.SAFE,
    (Mode.THERMAL_LIMIT, "fault"): Mode.FAULT,
    (Mode.LOW_POWER, "recover"): Mode.IDLE,
    (Mode.LOW_POWER, "safe"): Mode.SAFE,
    (Mode.LOW_POWER, "fault"): Mode.FAULT,
    (Mode.SAFE, "recover"): Mode.IDLE,
    (Mode.SAFE, "fault"): Mode.FAULT,
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


# Lightweight mode classification (ADR 0028). Operational modes run a
# workload and are where auto-safing fires from; impaired modes are
# safed-but-recoverable; terminal modes leave only via ``reset``. The rest
# (STOWED, BOOT, IDLE, SAFE) are transitional or holding states that belong
# to no bucket.
_OPERATIONAL_MODES = frozenset(
    {Mode.MISSION, Mode.RELAY, Mode.MONITORING, Mode.C2}
)
_IMPAIRED_MODES = frozenset(
    {Mode.DEGRADED, Mode.THERMAL_LIMIT, Mode.LOW_POWER}
)
_TERMINAL_MODES = frozenset({Mode.SHUTDOWN, Mode.FAULT})


def is_operational(mode: Mode) -> bool:
    """True for a mode that runs a workload (MISSION/RELAY/MONITORING/C2)."""
    return mode in _OPERATIONAL_MODES


def is_impaired(mode: Mode) -> bool:
    """True for a safed-but-recoverable mode (DEGRADED/THERMAL_LIMIT/LOW_POWER)."""
    return mode in _IMPAIRED_MODES


def is_terminal(mode: Mode) -> bool:
    """True for a mode that leaves only via ``reset`` (SHUTDOWN/FAULT)."""
    return mode in _TERMINAL_MODES


SC_THERMAL_HEADROOM = "SC-2"
SC_POWER_RESERVE = "SC-8"

# Label-namespaced requirement constraint ids (ADR 0028, ADR 0043). The id
# names the hazard the requirement guards against, so a mode-entry refusal and
# the matching auto-safe decision (``engine._safing_decision``) carry one
# constraint id per condition: one flag set, read at entry and at exit. The
# ``label:`` namespace keeps them distinct from the SC-* STPA ids.
REQ_OPERATOR = "label:operator-incapacitated"
REQ_COMMS_LINK = "label:comms-denied"


class _SafetyGate(NamedTuple):
    """One constraint a transition must satisfy, and the context key it judges."""

    constraint_id: str
    candidate_key: str


_GATE_THERMAL = _SafetyGate(SC_THERMAL_HEADROOM, "thermal_headroom_c")
_GATE_POWER = _SafetyGate(SC_POWER_RESERVE, "soc_pct")
_GATE_OPERATOR = _SafetyGate(REQ_OPERATOR, "operator_state")
_GATE_COMMS = _SafetyGate(REQ_COMMS_LINK, "comms_state")

# Each operational-mode entry from IDLE declares its full precondition set, the
# same conditions the auto-safe watches on the way out (ADR 0043). All four
# require thermal headroom (SC-2), battery reserve (SC-8), and an available
# operator (not incapacitated); the link-bearing modes (RELAY / C2) also
# require a live comms link, so a controller cannot enter a relay posture into
# a dead link and have it degrade only on the next tick. The recover/cool
# transitions out of an impaired mode land in IDLE but stay gated on the device
# hazards, so the device cannot leave the impaired posture until they clear
# (ADR 0029); IDLE is a standby, not an operational mode, so they carry no
# operator or comms requirement. The failsafe exits (safe / shutdown) are never
# gated. Gates are checked in order, device hazards first, so the established
# SC-2 / SC-8 refusal messages keep surfacing and the first unsatisfied
# constraint is the one the refusal names.
_SAFETY_GATES: dict[tuple[Mode, str], tuple[_SafetyGate, ...]] = {
    (Mode.IDLE, "mission"): (_GATE_THERMAL, _GATE_POWER, _GATE_OPERATOR),
    (Mode.IDLE, "relay"): (_GATE_THERMAL, _GATE_POWER, _GATE_OPERATOR, _GATE_COMMS),
    (Mode.IDLE, "monitoring"): (_GATE_THERMAL, _GATE_POWER, _GATE_OPERATOR),
    (Mode.IDLE, "c2"): (_GATE_THERMAL, _GATE_POWER, _GATE_OPERATOR, _GATE_COMMS),
    (Mode.DEGRADED, "recover"): (_GATE_THERMAL, _GATE_POWER),
    (Mode.THERMAL_LIMIT, "cool"): (_GATE_THERMAL, _GATE_POWER),
    (Mode.LOW_POWER, "recover"): (_GATE_THERMAL, _GATE_POWER),
}


def register_fsm_constraints(enforcer: SafetyEnforcer) -> None:
    """Register the FSM's safety-gate evaluators on ``enforcer``.

    SC-2 floors thermal headroom at the profile threshold; SC-8 floors
    state-of-charge at the profile's critical reserve. The operator and
    comms-link requirements refuse when their label reads incapacitated or
    denied. All four fail closed on missing context (ADR 0018, ADR 0022,
    ADR 0043).
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
    enforcer.register(
        REQ_OPERATOR,
        forbid_value(OperatorState.INCAPACITATED.value, label="operator"),
    )
    enforcer.register(
        REQ_COMMS_LINK,
        forbid_value(CommsState.DENIED.value, label="comms link"),
    )


def build_fsm_enforcer() -> SafetyEnforcer:
    """A :class:`~nous.safety.SafetyEnforcer` with the FSM safety gates registered."""
    enforcer = SafetyEnforcer()
    register_fsm_constraints(enforcer)
    return enforcer


# Cap on the in-memory transition and refusal logs (ADR 0029). The durable
# record is the SQLite ``state_transitions`` table; these deques only back the
# ``state_history`` in-memory fallback (which reads the last 256 rows), so a
# long-running server does not accumulate them without bound.
_HISTORY_MAXLEN = 512


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
        self._history: deque[tuple[Mode, str, Mode]] = deque(maxlen=_HISTORY_MAXLEN)
        self._refusals: deque[tuple[Mode, str, Mode, str]] = deque(
            maxlen=_HISTORY_MAXLEN
        )
        self._last_checks: list[SafetyResult] = []

    @property
    def current(self) -> Mode:
        return self._current

    def can(self, trigger: str) -> bool:
        """True if the table admits ``trigger`` from the current mode.

        Consults the transition table only, not the safety gates: a gated
        transition can still be refused by the enforcer at :meth:`transition`
        time. ``can`` answers "is this edge in the table," not "would it pass."
        """
        return (self._current, trigger) in _TRANSITIONS

    def would(self, trigger: str) -> Mode | None:
        """Return the table destination for ``trigger``, else ``None``.

        Table-only, like :meth:`can`: a returned mode is the edge's target, not
        a promise the gate will admit it.
        """
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

        A hard reseat for tests and tooling that need a known starting mode. It
        bypasses the table and the gates and writes no audit record, so it is
        not on the engine's restart path: :meth:`Engine.start` threads the
        ``reset`` trigger through the table instead.
        """
        self._current = mode
