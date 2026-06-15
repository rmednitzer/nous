# ADR 0058: Read estimator rejections through health, and stringify decode keys

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0007, ADR 0011, ADR 0045

## Context

Two findings from the 2026-06-14b audit touch a high-blast Protocol surface.
MED-3: the `Estimator` Protocol (`estimators/base.py`) declares `name` /
`predict` / `update` / `state`, but `position_status` / `sensors_status` /
`biometrics_status` read `est.rejected_updates` as a bare attribute. Only three
of the nine estimators expose that property, so a future estimator that
satisfies the Protocol without it would raise `AttributeError` inside a T0
status read. The literal remediation is to add `rejected_updates` to the
Protocol, but ADR 0045 already chose the opposite shape for exactly this kind of
diagnostic: filter health rides inside the `Estimate` returned by `state()` (the
optional `EstimatorHealth` block), so the Protocol stays at three methods and a
consumer reads diagnostics through `state()`. The `rejected_updates` field
already lives on `EstimatorHealth`; the tool was reaching around the contract to
read a parallel attribute.

LOW-4: the `Adapter` Protocol (`interop/base.py`) types `decode` as
`Mapping[str, Any]`, but nothing enforces string keys at runtime. The
`interop_decode` tool passes the decoded mapping to `json.dumps`, which coerces
scalar keys (an integer becomes its string form) but raises `TypeError` on a key
it cannot coerce. No shipped adapter trips this today (MISB KLV nests integer
tag numbers, which `json.dumps` coerces silently), but a future CBOR or msgpack
adapter could return a key that turns a decode call into an exception body.

## Decision

For MED-3, the three status tools read the rejection count through the `Estimate`
contract, not a bare attribute: a small `_rejected_from_health` helper returns
`estimate.health.rejected_updates`, or zero when an estimator reports no health
block. The `Estimator` Protocol is left at its three methods, consistent with
ADR 0045; the existing `rejected_updates` properties on the three estimators
stay (their unit tests pin them) but are no longer the tool's read path. This
closes the `AttributeError` exposure: any estimator that satisfies the Protocol
satisfies the tool, because the tool only calls `state()`. One consequence is a
semantics shift on two reads: `EstimatorHealth.rejected_updates` is
input-validation rejections plus innovation-gate rejections, whereas the
`BiometricsKalman` and `EnvironmentalKalman` properties counted only the former.
Their `rejected_updates` now includes gate rejections, which is the more
complete count, matches what `PositionKalman` already reported, and matches what
the self-model already surfaced through `health.model_dump()`. On a run with no
gate rejections (the common case) the number is unchanged at zero.

For LOW-4, `interop_decode` stringifies every mapping key recursively before
`json.dumps`, so a structurally valid but non-string-keyed payload serialises
rather than raising. The `decode` contract docstring is tightened to state that
keys should be strings and that the tool backstops a codec that returns
otherwise. The adapters are unchanged; the coercion is a tool-boundary safety
net, not a new adapter obligation, and MISB's integer tag keys serialise exactly
as before (`json.dumps` was already coercing them).

## Consequences

A Protocol-conforming estimator can be swapped in without an `AttributeError` in
a status read, and the estimator layer keeps the ADR 0045 shape (diagnostics in
`Estimate`, not the Protocol). The decode tool cannot be turned into an
exception body by a non-string key from any present or future adapter. The cost
is the documented rejection-count semantics change on the biometrics and sensors
reads, and a recursive walk over the decoded structure on every decode call
(bounded by the payload size, negligible against the codec work). Neither
high-blast Protocol gains a member: `estimators/base.py` is untouched, and
`interop/base.py` changes only its docstring. Closes BL-094.

## Revisit triggers

If a consumer needs the input-validation rejection count separate from the gate
rejection count, split `EstimatorHealth` into the two rather than re-adding a
parallel attribute. If a future adapter needs to round-trip non-string keys
faithfully (not merely survive serialisation), the decode contract would need a
typed key model rather than a stringifying backstop.
