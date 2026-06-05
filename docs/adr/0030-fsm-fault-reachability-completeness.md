# ADR 0030: FSM completeness -- uniform fault reachability from every powered mode

- **Status:** Accepted
- **Date:** 2026-06-05
- **Authors:** rmednitzer
- **Builds on:** ADR 0004, ADR 0028, ADR 0029

## Context

A completeness and validity audit of the transition table after the ADR 0029
remediation walked every mode's outgoing edges against the failsafe
invariants. It found the table valid (no failsafe edge is gated, no edge
enters `STOWED` except `reset`, the classification buckets are disjoint, every
mode is reachable from `STOWED`) and one genuine gap.

The gap is in `fault` reachability. The reachability work guaranteed a direct
`fault` edge from every operational mode and from `DEGRADED`, but `THERMAL_LIMIT`,
`LOW_POWER`, and `SAFE` had none. A hardware fault is mode-independent and
unrecoverable, yet a fault detected while the device was throttled, in low
power, or in the safe hold could not be recorded as a direct transition to the
terminal `FAULT`. It reached `FAULT` only transitively (for example
`thermal_limit -safe-> safe -recover-> idle -fault-> fault`), and a controller
calling `request_transition("fault")` from `THERMAL_LIMIT` would simply be
refused. That left the unrecoverable terminal one rung short of the postures a
device is most likely to be in when hardware degrades.

The audit also confirmed two absences are intentional, not gaps. There are no
operational-to-operational edges (`mission` does not reach `c2` directly): the
four operational modes are a hub-and-spoke around `IDLE`, so every operational
entry is re-gated on SC-2/SC-8. And `BOOT` has no `safe` edge: it is a
transitional state with no workload to shed, so its failsafe is `fault` or
`shutdown`.

## Decision

Add the three missing failsafe edges `THERMAL_LIMIT -fault-> FAULT`,
`LOW_POWER -fault-> FAULT`, and `SAFE -fault-> FAULT`. The invariant is now
uniform and total over the powered modes: `FAULT` is reachable in exactly one
`fault` trigger from every powered mode (`BOOT`, `IDLE`, the four operational
modes, the three impaired modes, and `SAFE`). The new edges are ungated, like
every failsafe exit, because a fault must never be refused.

The reachability suite is strengthened to enforce this. The former
operational-only fault check becomes `test_fault_reachable_in_one_trigger_from_every_powered_mode`,
and a new `test_failsafe_edges_are_never_gated` makes the previously
prose-only "no failsafe edge is gated" claim a build-breaking assertion.

## Consequences

A controller that detects a hardware fault can escalate to `FAULT` directly
from any powered posture rather than orchestrating a multi-hop path through a
gated recovery. The change is purely additive to the table (47 to 50
transitions) and ungated, so it relaxes nothing: it only makes a strictly
safer terminal more reachable. Auto-safing is unaffected, because the
auto-safe control law never emits `fault` (it is controller or engine
initiated); there is no behavioural change to the tick loop.

Alternatives rejected:

- **Leave `fault` transitive.** `FAULT` was already reachable from the impaired
  modes through `SAFE`, so the device was not stranded. But the direct call was
  refused and the recovery hop is gated, so a fault response depended on the
  controller knowing the indirect path. A fault should be one trigger from
  anywhere it can occur.
- **Operational-to-operational edges.** Keeping the hub-and-spoke through
  `IDLE` means every operational entry is re-gated; direct edges would bypass
  or duplicate that gate.
- **Impaired-to-impaired edges.** Not added: they would complicate the
  one-way, convergent auto-safe property, and the model is to recover to `IDLE`
  and re-enter.
- **`safe` from `BOOT`.** `BOOT` is transitional with nothing to shed; the
  `safe`-reachability invariant stays scoped to the operational and impaired
  modes where a workload exists.

## Revisit triggers

- A new powered mode is added to the FSM (extend the fault-reachability
  invariant to cover it).
- The engine gains an automatic fault path (today `fault` is only controller or
  engine initiated, never auto-safed), which would warrant its own ADR.
