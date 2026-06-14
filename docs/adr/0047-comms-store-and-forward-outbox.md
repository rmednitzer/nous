# ADR 0047: Comms store-and-forward outbox with precedence triage

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0006, ADR 0033, ADR 0041

## Context

The comms send seam is fire-and-forget. `CommsSubsystem.tx` accepts bytes only
on a live link; on an aged-out, forced-down, or unknown link it returns zero,
and `comms_send`, `comms_publish`, and `self_model_publish` all report
`bytes_accepted: 0` and move on. The 2026-06-14 audit (finding COMMS-1) confirmed
the consequence on the running twin: with all three links denied, a
`comms_publish` of a CoT event encoded a complete 352-byte message and then
discarded it. For an appliance whose purpose is to stay legible to a controller
across an intermittent tactical link, dropping the device's own situation report
the moment comms degrade is the wrong failure mode, and it is exactly the moment
the controller most needs the message to survive.

The backlog already carries the full delay-tolerant-networking vision at BL-056
(custody transfer, BPv7 bundles, multi-hop mesh, replay), and LIMITATIONS L12
recorded store-and-forward as out of scope for v0.1. That full layer is a large
L3 effort. The controller needs the practical core now: hold a package when the
link cannot carry it, decide which packages matter when bandwidth is scarce, and
deliver them when the link recovers. The question this ADR answers is how to add
that core without reaching for the whole DTN stack and without disturbing the
existing comms contracts.

## Decision

Add a `CommsOutbox` (in `src/nous/state/comms_outbox.py`): a bounded,
precedence-ordered store-and-forward queue the engine owns alongside the comms
subsystem. A queued `OutboxPackage` carries its target link, byte size, military
message `Precedence` (routine, priority, immediate, flash), a `kind` tag, an
enqueue timestamp, and an optional time-to-live. The engine constructs one in
`__init__` and rebuilds it on `reload_profile`, reading an optional
`comms.outbox` profile section (`enabled`, `max_packages`, `max_bytes`,
`default_ttl_s`) defensively so an old profile keeps working at the defaults.

Three rules make the triage auditable. A flush walks packages by descending
precedence then enqueue order, so a scarce recovered link spends its budget on
the most important traffic first. A package is only ever evicted to make room
for a strictly higher-precedence one, so the queue never displaces important
traffic for trivial traffic and every drop is counted. A package past its
time-to-live is dropped (counted as expired) rather than shipped, the
store-and-forward analogue of the SC-4 freshness gate the adapters already
enforce at encode time. The engine drains the outbox each tick through
`flush_tick`, which budgets each link at its modelled per-tick capacity
(`bandwidth_bps * dt / 8`), so a recovered narrow link clears its backlog at its
real rate rather than instantly.

The tool surface grows by three, registered in `tools/subsystems.py` beside the
existing comms tools (the ADR 0033 precedent: keep a subsystem's reads and
writes together). `comms_enqueue` (T2) holds a package given either a raw byte
count or a `payload_hex` blob (the form `interop_encode` returns), tagged with a
precedence and a TTL. `comms_outbox` (T0) reads the queue depth, the
per-precedence and per-link breakdown, the head package, and the disposition
counters. `comms_flush` (T2) forces a triage-ordered drain. The two writers are
added to `policy.py`'s `_STATEFUL_TOOLS` and the reader to `_READ_ONLY_TOOLS`;
this is the additive-surface rule of ADR 0007, not a change to the
classification logic.

The scope is deliberately single-hop and below BL-056: no custody transfer, no
BPv7 bundle format, no multi-hop routing, no replay. The outbox is the practical
triage and store-and-forward layer; BL-056 remains the tracker for the full DTN
model.

## Consequences

A controller can now publish through a degraded or denied comms window and trust
that the message is held and delivered when the link returns, with the most
important traffic going first over whatever bandwidth recovers. The triage is
legible end to end: `comms_outbox` shows the queue and the counters, `snapshot`
carries a compact outbox block, and every enqueue and flush is audited at its
tier. The precedence model is the tactical idiom (routine through flash), so it
reads the same way a CoT or TAK operator would expect.

The cost is a new piece of engine state that the tick loop drains every tick.
The drain runs unguarded like the estimators rather than guarded like the
external tick hooks, because it is internal machinery: a raising flush is a bug
the tests must catch, not a containment case. The outbox is rebuilt fresh on a
profile reload, matching how the subsystems are rebuilt, so a reload discards any
queued packages; this is consistent with the reload discarding live link state
and is documented rather than hidden.

Alternatives rejected. A per-link queue living inside `CommsSubsystem` would
entangle the queue with the link physics and force the triage policy below the
subsystem boundary, where it is harder to read and test; the outbox sits beside
the subsystem instead, the way the `FailsafeArbiter` sits beside the FSM.
Changing the `comms_send` and `comms_publish` signatures to take a precedence and
auto-enqueue on failure would break the byte-faithful contracts ADR 0033
established and conflate immediate send with deferred send; the new tools keep
the two paths distinct and composable (encode with `interop_encode`, then
`comms_enqueue`). Building the full BL-056 DTN layer now would be a large L3
effort for a need the single-hop outbox already meets.

## Revisit triggers

- BL-056 lands the full DTN layer (custody, BPv7, mesh, replay), at which point
  the outbox becomes its single-hop special case or is absorbed into it.
- A propagation-aware comms model (BL-048) makes per-link delivery probabilistic,
  so the flush needs to model partial delivery rather than all-or-nothing `tx`.
- The queue depth or the per-tick drain cost shows up in the tick budget
  (BL-073), which would push the drain off the hot tick path.
