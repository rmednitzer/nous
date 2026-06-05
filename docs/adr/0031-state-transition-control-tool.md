# ADR 0031: Register the state_transition control tool

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0004, ADR 0007, ADR 0021, ADR 0022

## Context

The mission-posture FSM is a headline capability, but the registered tool
surface exposed only reads of it: `state_get` and `state_history`. The engine
seam that actuates a transition, `Engine.request_transition(trigger,
context)`, has existed since the FSM landed, `policy.py` has classified
`state_transition` as `STATEFUL` (T2) all along under the additive-surface
forward-classification rule (ADR 0007), and the STPA control structure
(`docs/stpa/06`, `docs/stpa/07`) names `state_transition` as a primary control
action. No tool ever wired it, so the classification and the safety analysis
described a control action a controller could not actually invoke.

The gap has an observable cost. `Engine.start()` fires `boot` (STOWED to BOOT)
but never `ready`, and the only caller of `ready` is the scenario runner. A
freshly-booted engine therefore parks in BOOT, and the live VM has no
registered path onward to IDLE or the operational modes. The 2026-06-06 audit
found the live device at `mode=boot` after roughly eight minutes of ticking,
with no registered tool able to advance it; the entire posture set
(`mission` / `relay` / `monitoring` / `c2`) was reachable only by encoding a
`state_transition` action inside `scenario_inject`.

## Decision

Register `state_transition` in `src/nous/tools/state.py` as a T2 tool that
wraps `Engine.request_transition`. It accepts a `trigger` and an optional
`context` map and returns `{ok, mode, reason}`; `ok=false` covers both an
unknown table edge and a safety-gate refusal, so the controller reads one
observable outcome instead of catching an exception. The engine merges its
live safety context under any caller-supplied `context`, so the SC-2 thermal
and SC-8 power gates judge real values on every operational entry.

This is purely the missing tool-surface wiring. `policy.py` is unchanged
(`state_transition` was already in `_STATEFUL_TOOLS`), and the FSM, the
`SafetyEnforcer`, and `request_transition` are untouched. ADR 0021 scopes
tool wiring as low blast radius provided the tier is correct, which it is. The
`scenario_inject` `state_transition` action stays as the batch/replay path;
both routes call the same engine seam, so there is no second actuation path to
keep in sync.

## Consequences

A controller can drive the mission posture directly (`ready` to IDLE, then the
gated `mission` / `relay` / `monitoring` / `c2`, and the ungated `safe` /
`shutdown` failsafe exits) rather than constructing a scenario injection. The
registered surface grows from thirty to thirty-one tools. Every call is
audited like any other, guard refusals are recorded with their reason, and the
hash-chain and daily-anchor properties are unaffected. The live device is no
longer stranded in BOOT once a controller issues `ready`.

Alternatives rejected:

- **Auto-advance BOOT to IDLE on a tick.** The device should not go
  operational without a controller (or scenario) commanding it. An autonomous
  `ready` would bypass the deliberate boot hold and contradict the STPA control
  structure, which puts the controller in charge of the posture.
- **Leave the FSM drivable only through `scenario_inject`.** That forces a
  controller to encode a posture change as a scenario action, hides the primary
  control action the STPA already names, and surprises a live operator whose
  device looks stuck in `boot`.
- **A coarse `set_posture(mode)` tool.** It would hide the trigger vocabulary
  and the table's gating. The trigger is the reviewed contract (ADR 0004); the
  tool exposes it directly rather than inventing a parallel one.

## Revisit triggers

- A higher-level posture-orchestration tool is wanted (for example, "go
  operational and choose the mode by mission type"), which would layer over
  `state_transition` rather than replace it.
- A transition needs structured arguments beyond a single `context` map, which
  would warrant a richer tool signature.
