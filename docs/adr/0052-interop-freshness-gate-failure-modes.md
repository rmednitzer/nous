# ADR 0052: Name the interop freshness gate's configuration faults distinctly from staleness

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0011

## Context

`assert_fresh` (`interop/base.py`) is the shared SC-4 gate every interop adapter
calls before it encodes: it refuses to encode when the source estimate is older
than the adapter's `max_age_s`, and returns the resolved source timestamp so the
adapter can stamp it into the payload. The 2026-06-14 audit raised two issues
with how the gate reports its edges.

ITP-1: when `max_age_s` is invalid (non-positive or NaN), the gate raised
`StaleEstimateError(adapter, 0.0, max_age_s)`, so the message read "source
estimate is 0.00s old ... SC-4 refuses encode". The refusal is correct (an
adapter with an unusable `max_age` cannot validate freshness, so failing closed
is right), but the diagnostic is a contradiction: it reports a brand-new estimate
as the reason for a staleness refusal, masking that the real fault is the
configuration. FRESH-1: `resolve_ts` returns a `ts_s` of `0.0` verbatim, since
`0.0` is a valid epoch (the simulation clock starts there) and only NaN or
negative values are treated as "missing". A caller that compares a sim-epoch `ts`
against a wall-clock `now_s` therefore sees an enormous age and trips the gate.

## Decision

ITP-1: keep the refusal as a `StaleEstimateError` so the fail-closed handling in
the interop and publish tools (which catch `StaleEstimateError` and return a
structured `ok: false`) is unchanged, but give the exception an optional `reason`
and use it for the configuration fault. `assert_fresh` now resolves the source
timestamp and computes the real age first, then on an invalid `max_age_s` raises
with that real age and a reason naming the misconfiguration
("max_age_s=... is not a positive duration") rather than a fabricated zero. The
genuine-staleness message is byte-for-byte unchanged, and `reason` defaults to
`None`, so the change is additive.

FRESH-1: leave `resolve_ts` returning `0.0` verbatim. Treating it as "missing"
would corrupt every legitimate sim-epoch-zero timestamp, trading a narrow edge
case for a semantic bug. The clock-consistency requirement is the caller's: a
`ts` and a `now_s` must be on the same clock. This is documented on `resolve_ts`
rather than enforced, because the gate cannot tell a sim clock from a wall clock.

## Consequences

An operator who misconfigures an adapter's `max_age` now gets an error that names
the misconfiguration and the real source age, instead of a self-contradictory
"0.00s old". The `StaleEstimateError` type and the tools' fail-closed catch are
preserved, so no caller behaviour changes; the new `reason` attribute is an
additive, optional field a caller may branch on to separate a config fault from
genuine staleness. `resolve_ts` is untouched apart from its docstring, so the
sim-epoch semantics and every existing adapter conformance test hold.

FRESH-1's exposure stays a documented caller responsibility rather than a silent
trap: a freshly built engine whose sim clock is still `0.0`, or an `at_min: 0`
scenario step, must tick before it encodes against a wall-clock `now`, or pass a
`now_s` on the sim clock. The self-model publish path already stamps the live
wall clock for both sides, so it is unaffected.

Alternatives rejected. Raising a distinct exception (a `ValueError`) for an
invalid `max_age` would escape the tools' `StaleEstimateError` handler and turn a
fail-closed refusal into an uncaught error that breaks the encode response; the
configuration fault is better surfaced through the same channel the refusal
already uses. Treating `ts_s == 0.0` as missing in `resolve_ts` was rejected as
above.

## Revisit triggers

- Adapters begin carrying a per-message `max_age` rather than a constructor
  constant, which would make the invalid-config branch reachable on hostile
  input at runtime and might justify a dedicated configuration-error type.
- A sim/wall clock unification removes the FRESH-1 clock-consistency burden, at
  which point `resolve_ts` could resolve a clock rather than trust the caller.
