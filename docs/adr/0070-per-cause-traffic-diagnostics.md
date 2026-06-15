# ADR 0070: Per-cause diagnostics for held and dropped traffic

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0047, ADR 0053, ADR 0062, ADR 0065, ADR 0068

## Context

The store-and-forward outbox and the DTN mesh each keep a single counter that
conflates distinct failure causes. The outbox bumps a per-package `attempts` on
every deferred delivery, whether the link aged out, a propagation-loss draw
dropped the transmission, an EMCON posture denied the emission, or the modelled
capacity collapsed to zero. The mesh bumps one `dropped_total`, whether a bundle
exceeded the hop limit, a best-effort forward was lost, a custody bundle
exhausted its retries, or a node store overflowed its cap. A controller reading
`comms_outbox` or `dtn_mesh` can see that traffic is not moving but not why,
which is exactly the legibility the twin exists to provide (the AGENTS.md realism
rule, and the package-triage focus of the comms work). This is
AUDIT-2026-06-15 L-3 / BL-108.

## Decision

Surface the cause without changing the existing aggregate contracts, via three
additive seams.

The comms `tx()` seam records why a send was not accepted. Each `Link` carries a
`last_tx_reason` string that `tx()` sets on every call to one of a small fixed
set (`sent`, `forced_down`, `emcon`, `no_capacity`, `empty`); the integer
byte-count return is unchanged, so every existing caller is unaffected. The
reason is the link's last-attempt attribution, read by the outbox flush rather
than published on `comms_status`.

The outbox tallies a cumulative `defer_causes` map alongside the per-package
`attempts`. At each deferral the flush attributes a cause: `link_down` when the
link is not live, `loss` on a Bernoulli propagation-loss draw, and the link's
`last_tx_reason` (`emcon` / `no_capacity`) when `tx()` rejects an
accepted-and-budgeted package. A budget-deferred package is not a failed attempt
and is not counted. `defer_causes` is added to the `comms_outbox` counters block.

The mesh splits `dropped_total` into a cumulative `drop_causes` map: `max_hops`
at the hop-limit guard, `forward_loss` for a lost best-effort forward,
`retry_exhausted` for a custody bundle past `custody_retries`, and
`store_overflow` for a BL-098 store-cap eviction. The aggregate `dropped_total`
stays the sum and is still persisted; `drop_causes` is a runtime within-process
attribution surfaced on the `dtn_mesh` read but not checkpointed, so after a
restart the aggregate carries forward while the breakdown restarts from the new
process (a persisted breakdown would need a schema migration for no operational
gain, consistent with the BL-100 `restore_lost` and BL-101 load-failure fields).

## Consequences

A controller can now read `comms_outbox.counters.defer_causes` and
`dtn_mesh.counters.drop_causes` and tell an operator-imposed silence (`emcon`)
from a dead link (`link_down`) from a saturated channel (`no_capacity` / `loss`),
and a hop-limit drop from a custody exhaustion from a store overflow. The change
is additive: the existing `attempts`, `dropped`, and `expired` counters are
unchanged, so no reader breaks. The cost is a string field per link and two small
maps; the mesh breakdown is process-local by design, with the persisted total as
the durable record.

## Revisit triggers

- A persisted per-cause history becomes a requirement (then the mesh breakdown
  moves into the snapshot behind a migration).
- A new `tx()` rejection guard or mesh drop site is added (extend the reason set
  and the cause map together).
