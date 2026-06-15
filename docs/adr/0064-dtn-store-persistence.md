# ADR 0064: Persisting the DTN store across a restart

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0002, ADR 0019, ADR 0061, ADR 0062, ADR 0063

## Context

ADR 0062 and ADR 0063 built the DTN overlay's routing and custody, and both
recorded the same deferral: the store survives a link drop, where a held bundle
re-routes when its contact recovers, but not a node restart. The `DtnMesh` is
in-memory, so `engine.reload_profile` rebuilds it fresh and a true process
restart starts from profile defaults; every in-flight and in-custody bundle is
lost. For a custody-transfer model that promises guaranteed delivery, losing a
guaranteed bundle to a reboot is the one failure the model exists to survive.
This is BL-056 increment 4, the replay increment the prior two ADRs named.

The device already carries a persistence seam. ADR 0002 put a WAL-journalled
SQLite database at `$NOUS_HOME/state.db`, today holding only the FSM transition
log. The decision here is to persist the DTN store through that same database
rather than a new sidecar file or an in-memory-only handoff, so the store
survives a real process restart and reuses the durability posture the project
already commits to.

## Decision

The `DtnMesh` gains a pure snapshot and restore seam: `snapshot(now_s)` returns
the whole-mesh state (every node's held bundles, the bounded dedup ledgers, the
disposition counters, and the next origination sequence) as a plain dict, and
`restore` rebuilds that state. The mesh stays free of any database dependency, so
the routing and custody unit tests still construct it without one.

A new `DtnStore` wrapper in `db.py` persists and loads a snapshot through two
SQLModel tables behind an Alembic migration. `dtn_bundles` is relational, one row
per held bundle keyed by its holder node; `dtn_meta` is a single row carrying the
scalars and the bounded dedup ledgers (the mesh-wide delivered-id list and the
per-node seen lists, JSON-encoded, since they are bounded auxiliary sets rather
than first-class entities). A checkpoint replaces the persisted store in one
transaction. Writes are best effort and carry only the exception class, never the
message, exactly like `StateTransitionLog`: a flaky database cannot stall the
tick loop, and a DB URL with credentials cannot leak through the `dtn_mesh` read.

The engine owns the `DtnStore`, built from the same engine handle the transition
log already holds, so no new constructor wiring is needed. It checkpoints after a
mutating tick, gated by a dirty flag so an idle mesh writes nothing, and restores
whenever a fresh `DtnMesh` is built, both on first boot and on a hot reload.
Because a true restart resets the simulated clock while a hot reload preserves
it, restore rebases each bundle's creation and expiry by the elapsed delta, so a
bundle keeps its remaining lifetime rather than its absolute expiry. The mesh is
inert without a `dtn` profile section and in the memory-only mode (a `None`
engine), so the feature is opt-in and every shipped profile is unchanged.

## Consequences

A controller can now restart the device and watch a custodial bundle resume its
journey rather than vanish, and the `dtn_mesh` read carries a `persistence` block
reporting whether the store is database-backed and healthy. The cost is a
checkpoint write per mutating tick, a delete-and-insert bounded by the store
size; an idle or disabled mesh writes nothing. The dedup ledgers ride as JSON in
the meta row rather than a third table, keeping the bundles, the meaningful
payload, relational while not over-normalising bounded bookkeeping. A node's
seen entries for bundles it has already forwarded are not all persisted; the
held bundles repopulate each node's seen on restore, and the mesh-wide delivered
ledger (the one that prevents a post-restart retransmit from double-delivering)
is persisted in full.

## Revisit triggers

Incremental checkpointing, writing only the rows that changed, would land if a
store grows large enough that a full rewrite per tick costs. A dedicated dedup
table would replace the JSON ledgers if a controller needs to query them
relationally. The `audit_entries` mirror (BL-065) is the closest precedent if SQL
over the DTN store is ever wanted beyond restart recovery.
