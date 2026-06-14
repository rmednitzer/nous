# ADR 0046: Declarative mode-requirements gate

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0018, ADR 0022, ADR 0027, ADR 0028
- **Note:** Renumbered from 0043 to resolve a filename collision with `0043-constant-time-token-verification`; the originating commit references the former number.

## Context

The FSM gated entry into an operational mode (MISSION, RELAY, MONITORING, C2)
on two constraints: SC-2 thermal headroom and SC-8 power reserve (ADR 0018,
wired through the runtime enforcer in ADR 0022). The auto-safe path, however,
watched a larger flag set on the way out: a confirmed operator incapacitation
drives the device to SAFE (ADR 0028), and a denied comms link degrades the
link-bearing modes whose function depends on it (ADR 0027).

That asymmetry was the gap a PX4-Autopilot audit put in focus. A controller
could enter RELAY into an already-dead link, or MISSION while the operator was
already incapacitated, because entry checked only thermal and power; the
posture then degraded reactively on the next tick rather than being refused up
front. PX4 avoids this by deriving both "can I enter this mode" and "what must
I fall back to" from one `failsafe_flags` set (HealthAndArmingChecks and the
failsafe framework read the same conditions). The simulator's job is to make
the device legible, and an admission that silently contradicts the very
condition the auto-safe is about to act on is not legible.

## Decision

The entry gate becomes the full, declarative precondition set for each
operational mode, the same flag set the auto-safe reads on exit. Two changes
carry it.

A categorical evaluator, `forbid_value`, joins the enforcer's numeric
`floor_threshold` and `ceiling_clamp`: it approves any label except a named
unsafe value and refuses fail-closed on an absent one. The FSM registers it
twice, for an available operator (refuse when the label reads incapacitated)
and a live comms link (refuse when the label reads denied).

The gate table then declares, per operational entry, the constraints it
requires. All four IDLE entries require thermal headroom, power reserve, and an
available operator; RELAY and C2 additionally require a live comms link. The
recover and cool transitions out of an impaired mode keep their thermal and
power gates only, because they land in IDLE, a standby rather than an
operational posture. Crucially the operator and comms constraint ids are the
same ones the auto-safe records, so an entry refusal and an auto-safe firing on
the same condition land under one `constraint_id` in the audit trail: one flag
set, read at entry and at exit. The operator and comms auto-safe decisions stay
label-driven and debounced (ADR 0028) rather than routed through the enforcer,
so the enforcer's violation counter reflects entry refusals for them; the SC-2
and SC-8 hazards, which the auto-safe also routes through the enforcer, are
counted in both directions. The device hazards stay first in the gate order, so
the established SC-2 and SC-8 refusal messages keep surfacing and a
multi-condition failure still names a device hazard first.

## Consequences

Easier: a controller can no longer commit to a mode whose precondition is
already violated, and the refusal names the failed requirement (no valid
operator, no comms link) the same way the SC-2 and SC-8 refusals already do.
Entry and exit can never disagree about a condition, because they read the same
flags through the same ids.

Harder: the gate context must now carry the operator and comms labels, which
the engine supplies from its derived FSM state. The entry gate reads the
current label without the auto-safe's debounce, so a transient single-tick
incapacitation reading can refuse an entry the controller then retries; that is
the conservative, fail-safe direction and the debounce stays where it belongs,
on the one-way auto-safe to SAFE.

## Revisit triggers

- A controller needs to see admissibility before acting: surface a read-only
  "can I enter mode X, and what blocks it" report (the shape of PX4's `can_run`
  bitfield) through `self_model_situation`, derived from the same requirements
  table, so the picture is available without attempting the transition.
- The safing side grows past one transition per tick: a first-class failsafe
  action framework (severity-ordered actions, per-condition hysteresis with an
  anti-toggle recharge, explicit clear-conditions) is the separate next step
  that the same shared flag set would feed.
