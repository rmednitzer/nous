# ADR 0067: EMCON metadata minimisation

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0033, ADR 0041, ADR 0065

## Context

EMCON increments 1 and 2 control whether and when the device emits: a named
profile lists the permitted links (ADR 0065) and an optional duty-cycle window
schedules the bursts (ADR 0066). Neither touches what a permitted emission
carries. An appliance under OPSEC discipline often must emit (a position report,
a status push) but wants the emission to give an interceptor as little as
possible: a coarse location instead of a metre-accurate fix, a presence flag
instead of a full biometric record, no optional identifiers. That is metadata
minimisation, the first follow-on ADR 0065 named, and it is the third axis of the
same posture: not whether, not when, but how much detail.

The publish path is the natural seam. `comms_publish` and `self_model_publish`
both compose a mapping and hand it to `encode_and_tx`, which encodes it through a
named interop adapter and accounts the wire bytes. A minimisation step placed
just before the encode coarsens every structured emission uniformly, regardless
of adapter, without touching the adapters themselves.

## Decision

A profile may carry a `minimize` policy alongside its `permit_links` and
`window`: `{ position_decimals, drop }`. `position_decimals` rounds recognised
position fields (`lat`, `lon`, `latitude`, `longitude`) to that many decimal
places, coarsening a fix to a grid cell (two decimals is roughly a kilometre, one
roughly ten); `drop` is a list of field names removed from the payload. The
policy is applied by `Emcon.minimize(data)` at the `encode_and_tx` seam, before
the adapter encodes, so the coarsened mapping is what gets encoded, transmitted,
and (if the link is silent) held in the outbox. A profile without a policy, and
the default `unrestricted` posture, return the data unchanged, so the layer is
inert exactly as for windows.

Minimisation operates on top-level fields of the published mapping, by key. This
keeps it adapter-agnostic and predictable, and it composes with the rest of
EMCON: a `low_pi` profile can permit only the cellular link, burst on a schedule,
and coarsen what it sends, all at once. The raw `comms_send` byte-accounting path
has no structured content and is deliberately untouched.

The `minimize` key is an additive extension of the `comms.emcon` profile schema
(the high-blast surface this increment touches, covered here). It is reported by
`emcon_status` as the active profile's `minimize` policy and the per-profile
`minimizers` map, so the controller can see what a restricted posture strips.

## Consequences

A controller can now compose a deliberately low-information emission under a
restricted posture and confirm, through `emcon_status` and the returned
`payload_hex`, exactly what was coarsened. The cost is one mapping pass at the
publish seam and a new policy to reason about. Because minimisation happens at
compose time, a message generated under a minimising posture stays coarsened even
if it is held in the outbox and shipped later under a different posture, which
matches the intent: the operator composed a minimal message.

The increment is intentionally narrow. It coarsens top-level position fields and
drops named top-level fields; it does not recurse into nested structures (a
self-model situation's nested position is not yet reached), express a
metres-based grid, or redact a field to a placeholder token rather than removing
it. Those are the obvious follow-ons.

## Revisit triggers

Nested-field and per-adapter minimisation, a metres-based position grid, and
value redaction (presence tokens rather than removal) are the natural extensions
if a scenario needs them. A first-class `denied` audit record carrying EMCON
context remains the open BL-060 increment that touches the audit and runner
surfaces.
