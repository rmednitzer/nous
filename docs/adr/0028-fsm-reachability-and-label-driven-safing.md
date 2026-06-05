# ADR 0028: FSM failsafe reachability, classification, and label-driven safing

- **Status:** Accepted
- **Date:** 2026-06-05
- **Authors:** rmednitzer
- **Builds on:** ADR 0004, ADR 0018, ADR 0022, ADR 0027
- **Refined by:** ADR 0029 (recovery retargeted to IDLE), ADR 0030 (fault reachability from every powered mode)

## Context

The three prior FSM ADRs built the safety machinery from the entry boundary
inward: ADR 0018 and ADR 0022 gate a controller-requested entry on SC-2 and
SC-8, and ADR 0027 added the tick-driven loop that auto-safes out of
`MISSION` when those constraints are violated mid-run. Three gaps remained,
all of which ADR 0027 named as deferred to "the reachability work."

`SAFE` was not reachable in one step from an operational mode. It was wired
only from the impaired modes (`DEGRADED`, `THERMAL_LIMIT`, `LOW_POWER`), so
a controller (or the auto-safing loop) that wanted the full safe posture
from `MISSION` had to pass through `DEGRADED` first. That is why ADR 0027
could not act on the operator and viability conditions, whose natural target
is `SAFE`: there was no edge to take. `FAULT` was likewise unreachable from
`RELAY`/`MONITORING`/`C2`.

There was also no machine-checked guarantee that safety is reachable at all.
The transition table is small and finite, but nothing failed the build if a
refactor stranded a mode or wired an unguarded path into an operational
mode. The STPA constraints were enforced in code without a single artefact
tracing each safety-relevant transition back to its hazard.

## Decision

Add the missing fail-safe edges. Every operational mode
(`MISSION`/`RELAY`/`MONITORING`/`C2`) gets a direct `safe` trigger to
`SAFE`, and `RELAY`/`MONITORING`/`C2` get a `fault` trigger to `FAULT`
(`MISSION` already had one). None of these are gated: a path toward the
fail-safe state must be maximally reachable, never refused. The invariant
this establishes, and that the verification suite now checks, is that every
operational or impaired mode reaches `SAFE` in exactly one trigger.

Add a lightweight mode classification to `state/machine.py`:
`is_operational`, `is_impaired`, `is_terminal`, backed by frozensets. The
engine's auto-safing loop consumes `is_operational` instead of a private
copy, and the verification suite and STPA mapping use the buckets as their
vocabulary.

Extend the auto-safing loop with the two label-driven conditions ADR 0027
deferred. An operator derived as `INCAPACITATED` takes the full `safe`
posture, and it outranks the device hazards: when no one can supervise, the
safest hold is the right one regardless of the pack or the junction. A fully
denied comms link (`CommsState.DENIED`) degrades the link-bearing modes
(`RELAY`/`C2`), whose function depends on it; a `MISSION` or `MONITORING` run
that does not need comms is left alone. The SC-8 and SC-2 enforcer rules keep
their place between the two, so the priority is operator, then power, then
thermal, then comms. The label conditions read the derived state labels (the
operator label from the biometrics Kalman estimate, the comms label from the
per-link reported state), and each fires through the same one-way, audited
path as the enforcer rules. ADR 0029 later debounces the operator label,
because it is the estimate-sourced one, and leaves the reported-state comms
label instantaneous.

Verify the structure with exhaustive walks over the table (every mode
reachable from `STOWED`; `SAFE` and `SHUTDOWN` reachable from every
operating or impaired mode; every entry into an operational mode gated;
terminal modes leave only via `reset`) and trace each safety-relevant
transition to its constraint and hazard in
`docs/stpa/10-fsm-constraints-mapping.md`.

The non-`MISSION` operational modes keep the `degrade` fallback for SC-2 and
SC-8 rather than gaining their own `thermal_limit`/`low_power` edges.
`THERMAL_LIMIT` and `LOW_POWER` recover only to `MISSION`, so routing a
`RELAY` through them would silently change the mode it recovers into;
`DEGRADED` recovers to `MISSION` the same way and honestly means "a
subsystem is outside its envelope," which a throttling junction or a
stressed pack is.

## Consequences

Easier: the fail-safe guarantee is now a tested invariant rather than a
property a reader has to reconstruct from the table. The operator and comms
conditions are wired (closing the BL-004 auto-trigger), and the STPA mapping
gives a conformity reviewer a mechanical join from transition to hazard. The
classification helpers give the rest of the codebase a single vocabulary for
"is this mode operating."

Harder: the transition table grows from thirty-eight entries to forty-five.
That is still inside the one-screen budget ADR 0004 set and well under the
~50-mode revisit trigger (which counts modes, not transitions; the mode
count is unchanged at thirteen). The auto-safing priority list now has four
tiers, which is the point at which a declarative table parallel to
`_SAFETY_GATES` would start to pay off; ADR 0027's revisit trigger already
flags that.

Alternatives rejected:

- **Per-mode `thermal_limit`/`low_power` edges from every operational
  mode.** Couples to the recovery paths, which only return to `MISSION`; the
  `degrade` fallback is cleaner and recovers identically.
- **Gating the `safe` edges.** Backwards: the fail-safe transition is the
  one path that must never be refused.
- **Randomised (Hypothesis) reachability checks.** The state space is small
  and finite, so an exhaustive walk is both cheaper and a stronger
  guarantee than sampling.

## Revisit triggers

- A standing `viability=false` condition needs auto-safing; it joins the
  operator tier and may want its own `safe` rationale.
- The auto-safing priority list outgrows four tiers and wants a declarative
  table (shared with ADR 0027's trigger).
- The mode count approaches the ADR 0004 revisit threshold and the
  hand-rolled table stops fitting on a screen.
