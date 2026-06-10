# ADR 0041: Self-model publish target

- **Status:** Accepted
- **Date:** 2026-06-09
- **Authors:** rmednitzer
- **Builds on:** ADR 0010, ADR 0011, ADR 0033, ADR 0038

## Context

`self_model_publish` was classified T2 from L0 but never registered because
"publish the self-model" had no settled target; ADR 0033 listed the
candidates (a comms link? the audit log? a CoT detail block?) and deferred
the tool until a design existed. Since then `comms_publish` (ADR 0033)
established the project's publish seam -- shape a payload for an interop
adapter, encode it to wire bytes, account the bytes on a comms link -- and
`self_model_situation` (ADR 0038) produced the read worth publishing: one
fused, provenance-carrying situational picture. The STPA's H-1 hazard
("the self-model publishes a capability claim the device cannot honour")
also reads better with a concrete publish surface to point at.

## Decision

Register `self_model_publish(link_id, adapter, kind)` (T2) in
`tools/self_model.py`, composing the self-model read with the interop
registry and the comms `tx` seam, exactly the `comms_publish` path. `kind`
selects the read: `situation` (the ADR 0038 fused payload) or `assess` (the
capability claims plus explanation). The tool shapes the read into each
adapter's idiomatic envelope: MQTT carries the full payload, SensorThings
carries it as the Observation `result`, STANAG 4774 wraps it as the
labelled `payload`, and CoT emits a position event (estimated lat/lon/alt)
with a one-line capability summary in `remarks`. The pure position codecs
(`nmea0183`, `misb_klv`) have no generic payload channel and are refused.

Two honesty rules carry over. The simulated clock stays nested below the
envelope's top level so the SC-4 freshness gate reads the wall clock of the
live read rather than a sim-epoch offset that would always look stale; the
gate therefore certifies that the *read* is fresh (it is computed at call
time), while the staleness of each underlying estimator is carried inside
the payload itself (the situation read's per-driver `age_s`), which is the
honest place for it -- sim-clock estimator lag is not commensurable with a
wall-clock `max_age_s`. And the position fields CoT carries come from the
position estimator, not ground truth: a published claim is the estimator's
belief, which is the self-model's whole posture. No policy change; the surface grows from
forty-two to forty-three, and every remaining unregistered name is now
unregistered by design (`inference_request` redundant, `db_reset` /
`audit_rotate` operator-only).

## Consequences

A controller can push the device's self-assessment into the same modelled
egress path as any other telemetry and see its byte cost on the link
envelope, closing the last "needs design" deferral from ADR 0033. The H-1
hazard gains a concrete code seam the STPA can reference. As with
`comms_publish`, the publish is modelled (LIMITATIONS L2): bytes are
accounted, not transmitted.

Alternatives rejected:

- **Publishing into the audit log.** The audit trail records what the
  device did, hashed; it is not a telemetry bus, and writing controller-
  shaped payloads into it would weaken the chain's meaning (ADR 0025).
- **A new self-model wire format.** Six adapters already exist behind one
  Protocol (ADR 0011); inventing a seventh shape for this one read would
  bypass the registry the rest of the surface shares.
- **Restricting to MQTT only.** The shaping cost per adapter is a few
  lines, and the CoT form (position plus capability remarks) is the TAK
  story the interop layer exists for.

## Revisit triggers

- A new adapter joins `nous.interop.REGISTRY`: decide its self-model
  envelope (extend the shaping table) or record that it is refused; the
  tool fails closed for unshaped names, so the omission is safe but must
  not stay silent.
- A consumer needs the full situation payload inside CoT (a structured
  `<detail>` block rather than the remarks line).
- A real egress client is paired with the modelled publish (deployment
  concern; would need a posture review per LIMITATIONS L2).
- The situation payload grows past the adapters' `max_payload_len` bounds.
