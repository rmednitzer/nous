# ADR 0033: Complete the registered tool surface

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0007, ADR 0011, ADR 0021, ADR 0031, ADR 0032

## Context

ADR 0007's additive-surface rule lets `policy.py` forward-classify a tool name
before it is registered, so a tool ships at its intended tier instead of the
STATEFUL default. Across the L1/L2 rollout that left a tail of names classified
but never wired, which the 2026-06-06 audit recorded as finding F. ADR 0031
registered `state_transition`, and ADR 0032 registered the two `state_force_*`
tools and retired the dead `request_transition` entry. This ADR closes the
rest: it registers the names that already have an engine seam, and records an
explicit disposition for every name that does not, so "classified but
unregistered" is a decision with a reason rather than drift.

## Decision

Register `comms_send` and `comms_publish` (T2) in `tools/subsystems.py` beside
the comms reads (the `state.py` precedent: a capability module holds both its
reads and its writes). `comms_send` wraps the comms subsystem's `tx` seam:
record a transmission of N bytes on a link, which resets the age-out timer,
updates the coarse throughput, and rejects an unknown or forced-down link.
`comms_publish` composes the interop registry (BL-041) with `tx`: it encodes a
message through a named adapter and accounts the encoded byte size against the
link, returning the wire bytes (hex) and the accepted count. Both wrap existing
seams and both were already classified T2, so there is no policy change. The
tool surface grows from thirty-three to thirty-five.

The remaining classified-but-unregistered names are dispositioned, not left
implicit:

- `scenario_status` (T0) and `scenario_pause` / `scenario_resume` /
  `scenario_reset` (T1): the scenario runner is a synchronous one-shot
  (`run_scenario` walks a timeline and returns a report), so there is no
  running-scenario state to read, pause, resume, or reset. The snapshot's
  `scenario` field is the static startup setting, not live progress. These wait
  on a stateful, long-running scenario runner; deferred and tracked in the
  backlog.
- `tick_advance` (T1): the engine ticks at process scope (ADR 0024). A tool
  that called `Engine.tick()` would race the running loop, so a safe manual
  step needs a pause-the-loop-then-step design rather than a bare wrapper.
  Deferred.
- `inference_cloud` (T2) and `inference_request` (T2): the cloud inference path
  is deferred by design (BL-013, LIMITATIONS L4) pending its own ADR. The daily
  cap, the `CapExhausted` payload, and the fallback ladder are built, but
  exposing cloud inference on the controller surface is a product decision left
  open. (Superseded by ADR 0034, which makes that decision and registers
  `inference_cloud` over the fallback ladder; `inference_request` stays deferred
  as a redundant twin, since the ladder already routes cloud-or-local.)
- `self_model_publish` (T2): "publish the self-model" has no settled target (a
  comms link? the audit log? a CoT detail block?), so it needs a design before
  a tier-2 mutator is justified. Deferred.
- `db_reset` and `audit_rotate` (T3): operator and sysadmin maintenance
  actions, deliberately off the LLM-controller surface (ADR 0032). They stay
  classified so an operator-only surface, if one is ever added, inherits the
  tier.

After this ADR every name in `policy.py` is either registered or carries a
recorded reason for staying unregistered, so finding F is closed.

## Consequences

The comms control surface is now complete: reads (`comms_state`,
`comms_status`) plus writes (`comms_send`, `comms_publish`). A controller can
keep a link alive, simulate traffic, or publish a standards-shaped message and
see its byte cost on the link envelope, which is the first place the interop
and comms subsystems compose on the tool surface. Both tools are T2, so guarded
mode gates them like any other mutator. The disposition list above becomes the
checklist the next contributor consults before adding a forward-classified
name: register it when the seam lands, or record why not.

Alternatives rejected:

- **A dedicated `tools/comms.py` module.** The comms reads already live in the
  subsystems module; splitting the reads and writes for one subsystem across
  two files is less discoverable than keeping them together, and moving the
  reads would be churn for no contract change.
- **`comms_publish` actually transmitting to an external endpoint.** There is
  no hardware in the loop (LIMITATIONS L2); the modelled publish encodes the
  message and accounts its size against the link envelope, which is the honest
  simulator behaviour. Pairing the encoded bytes with a real wire client is a
  deployment concern, exactly as the MQTT conformance note already records.
- **Deleting the deferred names from `policy.py`.** Forward-classification is
  the point of ADR 0007: keeping the tier set means the tool ships correctly
  when its seam lands. The disposition list, not deletion, is the record.

## Revisit triggers

- A stateful scenario runner lands (unblocks `scenario_status` / `pause` /
  `resume` / `reset`).
- The cloud inference ADR lands (unblocks `inference_cloud` /
  `inference_request`).
- A self-model publish target is chosen (unblocks `self_model_publish`).

## Update (2026-06-09)

The first and third triggers fired. ADR 0040 lands the stateful scenario
session and registers `scenario_status` / `scenario_pause` /
`scenario_resume` / `scenario_reset` plus `tick_advance` (the session rides
an engine tick hook, which also dissolves the race this ADR feared for a
bare `tick_advance`). ADR 0041 settles the self-model publish target (the
`comms_publish` composition) and registers `self_model_publish`. The
remaining unregistered names are unregistered by design: `inference_request`
(redundant twin of `inference_cloud`, per the ADR 0034 note above) and the
operator-only `db_reset` / `audit_rotate`.
