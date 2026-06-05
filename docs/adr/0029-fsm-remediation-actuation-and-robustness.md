# ADR 0029: FSM remediation -- actuation, neutral recovery, and fail-closed robustness

- **Status:** Accepted
- **Date:** 2026-06-05
- **Authors:** rmednitzer
- **Builds on:** ADR 0018, ADR 0022, ADR 0027, ADR 0028

## Context

A full review of the state machine after the ADR 0018/0022/0027/0028 work
found the safety core correct (gate coverage complete, fail-closed airtight,
reachability machine-checked, one-way auto-safing convergent) but surfaced
one robustness bug, one behavioural surprise, and a cluster of places where
the safety ADRs claim more than the implementation delivers.

The headline gap is that the FSM mode was **observational**: no subsystem
read `state.mode`, so auto-safing relabelled and audited the posture but did
not actuate it. Entering `LOW_POWER` shed no load; the pack kept draining at
the same rate. That makes ADR 0027's "the load shed by `LOW_POWER` also
relieves heat" and "the device protects itself" false. The thermal throttle
(the one real mitigation) lives in the compute/thermal subsystems and fires
independently of the FSM.

The review also found: a non-numeric `power.soc_pct_critical_threshold`
crashes the tick loop (`_safety_context` does `float("oops")`) instead of
failing closed, reachable via the `profile_reload` tool; every impaired mode
recovers only to `MISSION`, so a degraded `RELAY`/`MONITORING`/`C2` silently
comes back as `MISSION`; the operator-incapacitation condition reads the
biometrics Kalman estimate, so a single-tick spike forces a one-way `SAFE`,
contradicting ADR 0027's "smooth truth, no debounce needed" rationale; the
generic `degrade` fallback is applied to the priority-1 operator condition
whose target should always be `safe`; `IDLE` cannot reach `SAFE`/`FAULT`;
`state.mode` is a hand-synced mirror of `fsm.current`; and the in-memory FSM
history is unbounded. ADR 0028 also claims the derived labels are
"estimator-sourced by construction," which is true for the operator label
but false for the comms label (it reads link reported-state).

## Decision

**Actuation (closes the observational gap).** The engine gains a single
mode-write seam, `_set_mode`, that updates the posture and runs entry
actions. Entering `SAFE`, `LOW_POWER`, or `THERMAL_LIMIT` caps the compute
subsystem's delivered load through a new `ComputeSubsystem.set_mode_load_ceiling`
that composes with the existing thermal-throttle ceiling (delivered load is
the min of the controller request and every active ceiling; the request is
preserved, so the cap lifts on return to an operational mode or `IDLE`). So
auto-safing to `LOW_POWER` now genuinely sheds load, lowers draw, and slows
the drain it was named for; `SAFE` drops to a minimal posture; the
`THERMAL_LIMIT` cap actively cools. The ceilings are module constants
(`SAFE` 5%, `LOW_POWER` 15%, `THERMAL_LIMIT` 40%); `DEGRADED` keeps full
load (it is the generic/comms posture, not a power or thermal command).

**Neutral recovery (removes the surprise).** `recover` and `cool` now target
`IDLE`, not `MISSION`. They stay gated on SC-2/SC-8, so a device cannot
leave an impaired posture until the hazard has cleared, but it lands in the
neutral `IDLE` and the controller re-selects the operational mode it wants
(re-gated). This eliminates the silent `RELAY -> MISSION` collapse and makes
recovery uniform with the existing `SAFE -> recover -> IDLE`. The failsafe
exits (`safe`, `shutdown`) stay ungated, so an impaired mode is never stuck.

**Debounced operator condition.** The operator-incapacitation auto-safe fires
only after the label has held `INCAPACITATED` for a few consecutive ticks
(`_OPERATOR_PERSISTENCE_TICKS = 3`). A single estimator spike no longer
forces a one-way `SAFE`. The SC-2/SC-8 and comms conditions stay
instantaneous: they read reported state, which the physics evolves smoothly.
So that the operator priority survives the debounce window even when a device
hazard co-occurs, the auto-safe is allowed to fire from an impaired mode, not
just an operational one. From an impaired mode the device-hazard and comms
conditions find no safer edge and no-op (and are skipped so they do not inflate
the violation counter); only a confirmed operator incapacitation acts there,
deepening `LOW_POWER`/`THERMAL_LIMIT`/`DEGRADED` to `SAFE`. Without this a
critical pack that safed to `LOW_POWER` on tick 1 would strand a
confirmed-incapacitated operator one rung short of the full safe posture ADR
0028 promises. The move stays one-way and convergent: `SAFE` has no auto edge
out.

**Per-condition fallback.** The auto-safe fallback is per-condition. The
operator condition demands `safe` and never downgrades to `degrade`; only the
enforcer (SC-8/SC-2) conditions fall back to `degrade`. A reachability
invariant guarantees `safe` from every operational mode, so the operator
condition always lands on `SAFE`.

**Fail closed on a malformed profile.** `ProfileModel` validates that the
safety-critical numeric fields (`power.soc_pct_critical_threshold`,
`thermal.headroom_threshold_c`) are numeric, so a bad profile is rejected at
load (and `reload_profile` keeps the previous good profile). As
defence-in-depth, `_safety_context` coerces the profile reserve defensively:
a non-numeric value is omitted, so the gate fails closed (refuses / auto-safes)
instead of crashing the tick loop.

**Failsafe from IDLE.** `IDLE` gains ungated `safe` and `fault` edges, so the
fail-safe and fault states are reachable from the holding state too.

**Single source of truth, bounded history.** `state.mode` is written only
through `_set_mode`. The FSM `_history` and `_refusals` are bounded deques.

The remaining review nits are documentation: the comms label is described as
reported-state-sourced (not estimator), the dead `StateMachine.reset()`
docstring is softened, and `can`/`would` are noted as table-only.

## Consequences

Easier: auto-safing now does what the docs say. The "sustains" half of H-2
and H-8 is genuinely mitigated, not just annotated: a verification test shows
`LOW_POWER` cutting draw and slowing the drain. Recovery no longer surprises.
A malformed profile fails closed. The mode write path is one seam, which is
also where actuation hangs, so a future entry action has one home.

Harder: the FSM mode now has a side effect (load), so a test that drives a
workload across an auto-safe must account for the cap; the recovery target
change touches several tests and the showcase scenarios (regenerated). The
compute subsystem gains a second ceiling. The transition table grows from
forty-five entries to forty-seven (the two new `IDLE` failsafe edges); ADR
0030 later takes it to fifty.

Accepted limitations (documented, not fixed here): the `device_info.safety`
violation counter still aggregates entry-gate refusals and the per-tick
auto-safe condition checks under one constraint id; separating them would
need a tagged counter and is deferred until a controller needs the
distinction. The mode load ceilings are constants rather than profile-driven.

Alternatives rejected:

- **Recovery to the pre-impairment origin mode.** Resumes the exact posture
  but needs the engine to override the table target dynamically, breaking the
  honest static table. Neutral `IDLE` plus an explicit re-select is simpler
  and matches the controller-in-the-loop model.
- **Debounce on all conditions.** Unnecessary for the reported-state
  conditions, which are smooth; only the estimate-sourced operator label
  needs it.
- **Profile-driven load ceilings.** Worth doing, but expands the profile
  schema and every profile file; constants ship now with a noted follow-up.

## Revisit triggers

- A controller needs to separate entry-refusal counts from auto-safe counts
  in the posture (split the counter).
- The mode load ceilings need to vary by hardware (move them into the
  profile schema).
- A second actuating entry action appears (generalise `_apply_mode_entry`
  into a table parallel to `_SAFETY_GATES`).
