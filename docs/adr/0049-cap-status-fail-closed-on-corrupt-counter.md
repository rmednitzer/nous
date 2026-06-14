# ADR 0049: Make the cap status read fail closed on a corrupt counter

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0005, ADR 0034

## Context

`CallCap` (`anthropic_client.py`) persists the daily cloud-call counter as one
JSON line and exposes two readers of it. `increment()` is the spend path: it is
called before every Claude request and refuses the call by raising
`CapExhausted` when the counter is corrupt, because a counter an attacker can
clobber with one bad write would otherwise defeat the cap (SC-5). `peek()` is
the status path: it feeds `anthropic_cap_status`, the tool a self-driving
controller polls to decide whether a cloud call is even worth attempting.

The two readers disagreed on a corrupt counter. `increment()` failed closed
(`CapExhausted`), but `peek()` failed open, returning `(0, cap)` for unparseable
JSON so `anthropic_cap_status` reported `available: true` with the full budget
remaining. The 2026-06-14 audit (CAP-1) found the consequence: a controller
polling the status tool saw a healthy cap at the same instant every
`inference_cloud` call was being silently downgraded to the local mock by the
fallback ladder's `CapExhausted` catch. The status surface lied about a
condition the spend path treats as fatal, which is exactly the kind of obscured
picture this twin exists to prevent. A second, smaller drift sat alongside it:
`increment()` parsed a non-integer `count` with a bare `int(...)` that raised a
raw `ValueError` rather than the documented `CapExhausted`.

## Decision

Route both readers through one parse helper, `_parse_count`, so they cannot
drift again. The helper returns `0` for the cases `increment()` already treats
as a fresh day (an empty file, valid JSON that is not an object, or a line
dated before today) and raises an internal `_CorruptCounter` for the cases
`increment()` must refuse (non-JSON, or a non-integer `count`).

`increment()` converts `_CorruptCounter` into `CapExhausted`, so it now fails
closed uniformly on any unparseable counter rather than leaking a `ValueError`
on the non-integer path. `peek()` returns a small frozen `CapReading`
(`count`, `cap`, `corrupt`); a corrupt counter yields `corrupt=True` instead of
a fabricated `count=0`. `anthropic_cap_status` reads the flag and reports a
corrupt counter as `available: false`, `exhausted: true`, `corrupt: true`, with
`remaining: 0` and `count_today: null`, so the polled status now matches what
the spend path would do, and an operator sees that the counter file needs
repair.

## Consequences

A controller can trust `anthropic_cap_status` again: it agrees with
`inference_cloud` by construction, because the same `_parse_count` decides both
"refuse the call" and "report unavailable". A corrupt counter surfaces as a
distinct `corrupt` state rather than masquerading as either a healthy cap or a
spent one, so the fallback to local inference is legible and the repair action
is obvious. The fix also tightens `increment()`: the non-integer `count` path
now fails closed with the documented exception instead of a raw `ValueError`.

The cost is a contract change on a high-blast surface. `peek()` returns
`CapReading` rather than a `(count, cap)` tuple; the four in-repo call sites
(the status renderer and three tests) are updated here, and the change is
covered by this ADR. `increment()` keeps its `(count, cap)` tuple return
untouched, since that is the widely consumed contract.

Alternatives rejected. Keeping the tuple and saturating `count` to `cap` on
corruption is dishonest: it conflates a corrupt counter with one legitimately at
the cap, and it cannot express refusal when the cap is disabled (`cap=0`), where
`increment()` still raises on a corrupt counter because the corruption check
precedes the cap check. Making `peek()` raise on corruption was rejected because
a status read must not propagate an exception through the audited runner; a
corrupt counter is a state to report, not a fault to throw.

## Revisit triggers

- The persisted counter grows fields beyond `date` and `count`, which would
  give `_parse_count` more to validate and possibly more failure modes to
  distinguish.
- A controller needs to tell corruption kinds apart (truncated write versus
  wrong type versus tampering), which would justify a richer `corrupt` signal
  than a single boolean.
