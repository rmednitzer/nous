# ADR 0060: inference_local stays T1 (reversible) despite its usage counters

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0001, ADR 0013, ADR 0034

## Context

The audited runner classifies every tool into a tier (T0 read-only, T1
reversible, T2 stateful, T3 irreversible) and the admission policy keys on it:
under guarded mode a T1 tool is admitted without an allowlist match, while a T2
or T3 tool is refused unless `NOUS_POLICY_ALLOW` matches (an operator's
`NOUS_POLICY_DENY` regex can still refuse any tool in any mode). `inference_local`
is T1. The
2026-06-14b audit (LOW-2) noted that `inference_local` increments three monotonic
counters (`local_calls`, `total_tokens`, `total_energy_j`) that no tool undoes,
which strains the literal T1 criterion ("trivially undone"), and that the T2
reading would change the guarded-mode contract. The disposition needed a
deliberate decision.

## Decision

`inference_local` stays T1. Three facts support keeping it reversible rather than
promoting it to the stateful tier.

The counters are pure accounting. `total_energy_j` records the joules a one-shot
call would consume and reports them to the caller for the audit trail, but
nothing reads them back into the simulation: the battery state-of-charge loop is
`compute.draw_w -> power.set_load_w -> SoC`, driven by `load_pct`, and the
inference counters never debit it (the `InferenceSubsystem` docstring documents
this boundary deliberately, so the estimator never sees a parallel SoC path).
Unbounded `inference_local` calls therefore exhaust no modelled resource; the
counters are telemetry, not state a controller must be gated from advancing.

The precedent is already set by `tick_advance`, also T1, which advances the
entire simulated clock and steps every subsystem's physics (including real SoC
drain and thermal accumulation) monotonically. A tool that advances three
accounting counters is a far weaker mutation than one that advances the whole
clock, so "advances a monotonic counter" is squarely inside the T1 envelope as
the project already draws it.

The tier also protects availability. Guarded mode is the locked-down posture a
controller adopts when the environment is hostile, which is precisely when comms
are degraded or denied and the local inference path is the fallback the device
relies on. Making `inference_local` T2 would refuse it under guarded mode unless
an operator had pre-loaded an allowlist entry, gating the one inference path that
is supposed to survive a comms outage. `inference_cloud` is correctly T2 for the
opposite reason: it consumes a unit of the finite daily cap and makes an external
call, both genuine side effects the guarded posture should gate.

## Consequences

No behaviour changes. `inference_local` keeps its T1 admission, a comment on its
`_REVERSIBLE_TOOLS` membership records why the counters do not promote it, and a
regression pin (`TestLow2InferenceLocalStaysReversibleT1`) asserts the tier and
the guarded-mode admission so a future reclassification is a deliberate, visible
change rather than a silent edit. The cost is that the audit trail, not the
admission tier, remains the only record of local-inference usage; an operator who
wants to rate-limit local inference must do so out of band (a cap analogous to
the cloud `CallCap` is a possible future addition, not part of this decision).

## Revisit triggers

Revisit if `inference_local` ever gains a real side effect, for example if a
one-shot call begins to debit battery SoC directly or consumes a finite local
budget, at which point the stateful tier (and a cap) would be warranted.
