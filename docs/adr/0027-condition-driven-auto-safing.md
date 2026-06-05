# ADR 0027: Condition-driven auto-safing on tick

- **Status:** Accepted
- **Date:** 2026-06-05
- **Authors:** rmednitzer
- **Builds on:** ADR 0004, ADR 0018, ADR 0022

## Context

ADR 0018 and ADR 0022 wired the FSM's entry guards: a controller request
to enter an operational mode is refused when SC-2 (thermal headroom) or
SC-8 (power reserve) is violated. That closes the "provided unsafely" UCA
at the mode boundary, but it leaves the "sustains" half of H-2 and H-8
open. A device admitted to `MISSION` while healthy can heat past its
throttle point or drain past its critical reserve and simply stay there:
`Engine.tick` advances the subsystem physics and the estimators, but it
never re-evaluates the constraints or moves the FSM. Nothing drives the
device toward a safer posture until a controller happens to look.

This is the gap `docs/backlog.md` tracks as BL-004 ("the FSM does not yet
auto-trigger on the derived labels") and BL-022 (DR-2). The PR that wired
ADR 0022 surfaced the same point in review: the entry gate alone does not
protect a long or high-load run.

The fix is a control loop the device runs on itself. On each tick, from an
operational mode, the engine asks the same enforcer that guards entry
whether the current state still satisfies the constraints. When it does
not, the engine moves the FSM toward the matching safer mode without
waiting for a controller.

## Decision

`Engine.tick` calls `_auto_safe` once per tick. It is a no-op unless the
FSM is in an operational mode (`MISSION`, `RELAY`, `MONITORING`, `C2`).
From an operational mode it evaluates the safety conditions in priority
order through the shared `SafetyEnforcer` (ADR 0022), against the same
reported-state safety context the entry gates read (ADR 0018, and the
truth-sourced decision recorded on the ADR 0022 wiring PR):

1. SC-8 power reserve. Power depletion is the least recoverable hazard,
   and the load shed by `LOW_POWER` also relieves thermal stress, so it is
   checked first.
2. SC-2 thermal headroom.

The first violated constraint fires one transition toward safety: the
mode-specific safer trigger when the table offers one (`low_power` for
SC-8, `thermal_limit` for SC-2, both defined from `MISSION`), otherwise
`degrade`, which every operational mode offers and which lands in
`DEGRADED` ("a subsystem is outside its envelope") honestly. At most one
auto-transition fires per tick; the next tick re-evaluates from whatever
mode resulted.

Auto-safing is one-way. The engine only ever moves *toward* a safer mode;
it never auto-recovers. Recovery stays controller-gated through the
existing `recover` and `cool` triggers, which the same enforcer re-checks,
so a device cannot bounce back into an operational mode while the hazard
persists. That one-way property is the hysteresis: with no auto-recovery
path there is no oscillation to damp, so the loop needs no debounce or
deadband. The signals it reads are subsystem truth, which the forward-Euler
physics evolves smoothly, not a noisy estimate, so a single spurious tick
cannot mis-fire it.

Every auto-safing decision is mirrored to the audit log under
`Tier.SAFETY` (tool `auto_safe`), carrying the violated constraint, the
value, and the evidence, the same projection the entry-gate mirror uses.
The transition itself is recorded to the SQLite transition log with an
`auto-safe:` reason so `state_history` distinguishes a self-initiated safe
from a controller-driven one.

## Consequences

Easier: the device protects itself on a long run. The "sustains" half of
H-2 and H-8 is closed for `MISSION`, which gains precise targeting
(`thermal_limit`, `low_power`), and the other operational modes degrade
rather than coasting on a dying pack or a throttling junction. The
behaviour is observable three ways: the `auto-safe:` rows in
`state_history`, the `Tier.SAFETY` audit records, and the enforcer
violation counter in `device_info`.

Harder: the FSM now changes mode without a controller call, so a tick loop
that previously held `MISSION` under an injected anomaly will now move.
Scenario expectations and tests that drive a hazard and assert the mode
stays put have to account for the safe transition. The change is scoped to
the tick loop; the pure-`request_transition` paths are unchanged.

Deferred to the reachability PR (the next in this series): the
label-driven conditions (comms `DENIED`, operator `INCAPACITATED`) and a
`viability=false` standing check. Their natural target is `SAFE`, which no
operational mode reaches directly today, so they land with the edges that
PR's reachability work adds (direct `safe` from every operational mode)
rather than being forced through `degrade` here. Until then, the
non-`MISSION` operational modes also fall back to `degrade` for SC-2/SC-8
rather than entering `THERMAL_LIMIT`/`LOW_POWER` directly, because those
edges do not yet exist from `RELAY`/`MONITORING`/`C2`.

Alternatives rejected:

- **Debounce or deadband on the conditions.** Unnecessary given one-way
  safing over a smooth truth signal; it would only delay protection.
- **Auto-recovery when the hazard clears.** Recovery must re-check the
  constraints and is a controller decision; an engine that auto-recovers
  invites oscillation and hides the event from the controller.
- **A separate watchdog process.** Splits the safety logic away from the
  tick loop that owns the physics and the enforcer; the loop is the right
  home.

## Revisit triggers

- The reachability PR adds direct `safe` and the per-mode
  `thermal_limit`/`low_power` edges; auto-safing should switch to the
  precise targets and pick up the label-driven and viability conditions.
- A condition needs a time-series window (sustained-for-N-ticks) rather
  than an instantaneous read; the one-shot evaluation grows a small
  per-condition persistence counter.
- The set of auto-safed conditions outgrows the priority list and needs a
  declarative table parallel to `_SAFETY_GATES`.
