# ADR 0011: Interoperability adapters as a single Protocol

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001

## Context

A backpack inference appliance has to speak the standards its peers
expect: CoT/TAK for situational awareness, OGC SensorThings for
environmental telemetry, MISB KLV for video metadata, NMEA 0183 for
position, STANAG 4774/4778 for confidentiality labelling, MQTT for
publish/subscribe. Each standard has its own encoder, parser, transport
quirks, and conformance posture. Treating them as a flat list of
ad-hoc modules invites duplication; treating them as plugins under a
single Protocol keeps the seam testable.

## Decision

Every interop adapter implements `src/nous/interop/base.Adapter`:
``encode(data) -> bytes`` and ``decode(payload) -> Mapping``. Streaming
adapters (CoT-over-TAK, MQTT) expose their own ``stream`` coroutine on
top of the base. The v0.1 adapters are CoT, SensorThings, MISB KLV,
NMEA 0183, STANAG 4774, and MQTT.

The conformance posture per standard lives under `docs/conformance/`.
Each adapter has a model card-style page that states what is supported,
what is omitted, and which version of the standard is targeted.

## Consequences

Easier: a new adapter is one Python file, one conformance page, one
test. The base Protocol is small enough to keep in working memory.

Harder: standards with stateful sessions (MQTT brokers, TAK servers)
need lifecycle hooks that the Protocol does not enumerate; concrete
adapters expose their own.

## Revisit triggers

- A standard requires a session model rich enough that the base
  Protocol is misleading.
- A deployment needs to negotiate adapters dynamically (currently
  static; chosen at config time).
