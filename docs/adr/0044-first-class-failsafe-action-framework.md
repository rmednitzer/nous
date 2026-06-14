# ADR 0044: First-class failsafe action framework

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0027, ADR 0028, ADR 0029, ADR 0046

## Context

The tick-loop auto-safe (`Engine._auto_safe` and `_safing_decision`) grew up
condition by condition. Operator incapacitation carried a bespoke debounce
counter (`_operator_incap_streak`), the device hazards (SC-8 power, SC-2
thermal) and the comms-denied condition fired instantaneously, the priority
order lived implicitly in the sequence of `if` checks, and each condition's
action (preferred trigger, fallback) was hand-written inline. It worked, and
ADR 0027 / 0028 / 0029 pinned its behaviour, but the policy was not legible in
one place and only one condition had any hysteresis.

A PX4-Autopilot audit named the pattern this should follow. PX4's failsafe
framework is declarative: each condition maps to an action through a table,
actions are selected by severity, and the hold delay recharges more slowly
than it discharges so a flapping condition cannot perpetually reset the grace
period. The recommendation for `nous` was to make hysteresis a first-class
per-condition property rather than a one-off, to select by an explicit
severity, and to keep the policy in a table a reader can audit at a glance.

## Decision

Split the safing law into a reusable framework and the engine's detectors,
the way PX4 separates `FailsafeBase` from the concrete `checkStateAndMode`.

`src/nous/state/failsafe.py` holds the framework: a declarative
`FailsafeCondition` (id, severity, debounce ticks, decay, preferred and
fallback triggers) and a pure `FailsafeArbiter`. The arbiter is fed the set of
raw-active condition ids each tick. It grows each active condition's streak
(capped at its debounce threshold) and decays each inactive one. The decay is
by one per clear tick rather than a reset to zero, so a sustained but noisy
condition still accrues toward firing: this is the anti-toggle the audit asked
for, with the decay rate left as a per-condition field. The arbiter then
selects the highest-severity condition whose streak has reached its threshold.

The engine keeps the detectors, which need its live state and the enforcer: it
builds the raw-active map (operator from the FSM label, the device hazards
through `SafetyEnforcer.check`, comms from the label scoped to the link modes),
feeds the arbiter, and fires the selected condition's trigger exactly as
before, one transition per tick. The condition table replaces `_SAFING_RULES`,
the `_operator_incap_streak` field, and the inline priority order. Recovery
stays controller-gated: the conditions never auto-clear into a less safe mode,
which is the deliberate one-way posture of ADR 0029, so the only PX4
clear-condition `nous` adopts is "cleared by the controller".

Existing behaviour is preserved. The device and comms conditions keep a
debounce of one tick (instantaneous), the operator condition keeps its
three-tick window (now with anti-toggle), and the severity order
(operator over power over thermal over comms) reproduces the previous
priority. The one deliberate change is the anti-toggle itself: a sustained
but flapping operator label can now cross the debounce where a hard reset
would have held it off forever. The operator condition stays label-driven
rather than routed through `SafetyEnforcer.check`, so this changes when the
label fires, not the enforcer's violation counter; only the SC-2 and SC-8
device hazards touch that counter, exactly as before.

## Consequences

Easier: the safing policy is one readable table, hysteresis is a per-condition
parameter rather than a special case, and the arbiter is a small pure unit
that can be tested in isolation (severity selection, debounce, anti-toggle)
without standing up an engine. Adding a debounce to the comms condition, or a
new condition, is now a table entry, not a new branch in a growing function.

Harder: there is one more module in the FSM layer, and a reader tracing a
single safing decision now crosses the engine detector and the arbiter rather
than reading one function. The audit-record shape, the constraint ids, and the
controller-gated recovery are unchanged, so the change is contained to how the
decision is reached, not what it does.

## Revisit triggers

- A condition needs a slower recharge than discharge (the full PX4 4:1): the
  `decay` field already carries it; widen the streak to a finer resolution if
  an integer decay proves too coarse.
- A failsafe should auto-clear when its condition clears (a departure from the
  one-way posture of ADR 0029): the framework would grow an explicit
  clear-condition per action, as PX4 has, and the FSM would need the matching
  recovery edges to be safe to take unattended.
