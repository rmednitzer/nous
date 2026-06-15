# ADR 0068: DTN custody-store bound and restore-loss accounting

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0061, ADR 0062, ADR 0063, ADR 0064

## Context

The 2026-06-15 audit (`docs/audit-2026-06-15.md`) raised three custody-robustness
gaps in the BL-056 DTN layer. Two are genuine and fixed here; the third is
re-assessed.

A node's custody store (`DtnNode.store`) had no bound. `originate()` accepts a
zero or absent lifetime (expiry `None`), and `step()` leaves a bundle whose
destination has no route in its holder's store indefinitely, so a stream of
unroutable or no-expiry bundles grows memory without bound and with no signal to
the controller (BL-098). Separately, `restore()` rebuilds the store from a
persisted snapshot and silently skips any bundle held by a node EID that is no
longer in the topology (a peer removed between restarts), so a custody bundle is
lost with no counter, log, or flag, and the controller cannot tell delivery from
loss (BL-100).

The audit also flagged a custody retransmit storm as O(custody_retries^N) over an
N-hop high-loss path (BL-099). On a closer read this is over-stated: the per-node
`seen` dedup admits a given bundle id to a node at most once, so live copies of a
bundle are bounded by the node count, not exponentially; and the per-bundle
`attempts <= custody_retries` cap, which `clone()` inherits and the bundle row
persists, bounds each lineage's retransmits across a restart. The unbounded risk
is the number of distinct stuck bundles, which is exactly BL-098.

## Decision

A node's store is bounded by a configurable `max_store` (the `dtn.max_store`
profile field, default 256). Admission goes through one seam, `_admit()`: a bundle
is appended, and while the store exceeds the cap the triage-worst held bundle (the
tail of triage order: lowest precedence, then newest) is dropped and counted in
`dropped_total`. Because a lower-precedence newcomer is itself the worst, it is
shed rather than displacing an equal-or-higher held bundle, the same precedence
discipline the BL-077 outbox uses. This bounds both the unroutable accumulation of
BL-098 and, as a consequence, the per-node copy count BL-099 worried about, so no
second retransmit cap is added beyond the existing `attempts` bound.

`restore()` now counts every bundle it skips because the holder node is absent
from the rebuilt topology into a `restore_lost_total`, surfaced in the `dtn_mesh`
read's counters next to the disposition totals. The count is a runtime observation
of the most recent restore rather than persisted disposition, so it is not written
back into the snapshot; the silent custody loss becomes visible without a schema
change.

The increment is deliberately migration-free. `max_store` is config, the
store-cap eviction reuses the persisted `dropped_total`, and `restore_lost_total`
is runtime, so neither the `dtn_bundles` nor the `dtn_meta` schema changes.
Splitting `dropped_total` by cause (store-cap, forward-loss, max-hops) is the
separate BL-108 diagnostics item.

## Consequences

A long-running scenario that originates faster than it delivers, or that targets
an unreachable peer, now sheds its lowest-priority backlog at a bounded store
rather than growing without limit, and the shedding is visible as `dropped`. An
operator who restarts the device into a changed topology sees `restore_lost` count
the custody bundles that could not be replaced, instead of a silent gap. The cost
is one bound to reason about and an eviction policy (triage-worst) that, like the
outbox, prefers precedence then age, so a flood of low-precedence traffic cannot
evict high-precedence custody bundles.

The retransmit accounting stays aggregate (`retransmits_total`); a per-bundle
retransmit count and a per-cause drop breakdown are deferred to BL-108. The
store-cap eviction is silent beyond the `dropped` counter; an operator who needs
to know which bundles were shed reads that same BL-108 diagnostics surface.

## Revisit triggers

Per-cause drop counters (BL-108) land if the conflated `dropped_total` proves too
coarse to diagnose a backlog. A persisted per-bundle retransmit count lands if the
`attempts`-based lineage cap proves insufficient in a deep multi-hop topology. A
per-precedence store reservation (so a low-precedence flood cannot fill the store
at all) is the natural follow-on if the flat cap proves too blunt.
