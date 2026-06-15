# ADR 0061: BPv7 bundle identity and a delivered-bundle ledger for the DTN layer

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0047

## Context

BL-077 / ADR 0047 gave the comms stack a single-hop store-and-forward outbox: a
bounded, precedence-ordered queue that holds packages a degraded link cannot
carry and flushes them in triage order as links recover. It is deliberately below
the full delay-tolerant-networking vision (BL-056). A queued package is an
anonymous `(link_id, size, precedence, kind)` tuple with no identity that
survives a hop, so nothing can deduplicate a re-submission, transfer custody to a
next hop, or replay a store on reconnect.

This ADR begins BL-056 with the foundation those features need: a BPv7-shaped
bundle identity on every queued package, and a bounded ledger of recently
delivered bundles so a re-submitted bundle is recognised rather than duplicated.
It does not add multi-hop custody transfer or mesh routing, which need a
peer-node model (the next increment); it makes the device's own packages
identifiable and idempotent.

## Decision

Every queued package carries a bundle identity modelled on the BPv7 (RFC 9171)
primary block: a source endpoint identifier (the device's node EID), a
destination EID, a creation timestamp (the simulated enqueue time, ADR 0019), and
a creation sequence number, with a canonical `bundle_id` string form. The node
EID defaults to `dtn://<profile-name>/` and is overridable via `comms.node_eid`;
the destination defaults to `dtn://controller/`, overridable per enqueue or via
`comms.peer_eid`. Lifetime is the existing TTL, which is the BPv7 bundle lifetime
by another name, so no new expiry path is introduced.

Enqueue assigns a fresh monotonic sequence and a unique `bundle_id` unless the
caller supplies an explicit `bundle_id`, which makes the call idempotent: a
caller re-submitting the same situation report after a perceived failure passes
the same id. The outbox keeps a bounded ledger (a fixed-size window) of recently
delivered `bundle_id`s; an enqueue whose id is already queued or already in the
ledger is refused as a duplicate and counted, so a flaky controller that retries
does not flush the same bundle twice. The ledger is bounded, so dedup is a
recent-window guarantee, not an all-time one (consistent with DTN dedup windows);
a bundle older than the window re-enters as new.

The change is additive. A package enqueued without a `bundle_id` (every existing
caller and test) gets a unique auto-id, so it can never collide and the queue,
triage, flush, and expiry behaviour are byte-for-byte unchanged; only the
surfaced metadata and the opt-in dedup are new.

## Consequences

A controller can now name a package and ask whether a specific bundle was
delivered, and a retry of the same bundle is idempotent instead of doubling the
queue. The identity is the seam the next increments build on: custody transfer
hands a named bundle to a peer that acknowledges it, and replay re-offers stored
bundles by id. The cost is a few fields per package and a bounded ledger, and the
dedup window is finite by design. The EID scheme is `dtn:`-shaped for legibility
but is a string label, not a routed address (there is no peer to route to yet).

## Revisit triggers

The peer-node and custody-transfer increment (BL-056) adds custody signals and
retransmission on top of this identity; revisit the ledger bound and the dedup
semantics then, since custody transfer changes "delivered" from "handed to the
link" to "acknowledged by the next custodian."
