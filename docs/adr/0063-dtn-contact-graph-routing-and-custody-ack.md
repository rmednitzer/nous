# ADR 0063: Contact-graph routing and an explicit custody acknowledgement

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0047, ADR 0061, ADR 0062

## Context

ADR 0062 gave the DTN mesh a working multi-hop core but recorded two
simplifications for this increment to revisit. Routing was a hop-count shortest
path over the contacts that happen to be up at the instant of the tick, and the
custody acknowledgement was folded into forward success rather than modelled as
its own event. Both hold up only when a contact is either up or down for the
whole run.

Delay-tolerant networking exists for the case those simplifications miss:
contacts that are scheduled or intermittent, where no end-to-end path is up at
once and a node must carry a bundle toward a contact that has not opened yet.
Instantaneous shortest path holds a bundle whenever its next contact is
currently down, even when that contact is scheduled to open in time to still
meet the bundle's deadline, so it never plans ahead. And a custody handshake
folded into forward success can never produce the duplicate a real,
separately-lossy acknowledgement produces, so the reliability story stops short
of the one failure custody transfer exists to survive.

## Decision

Two coupled changes, both additive and inert unless configured.

**Timed contacts and contact-graph routing.** A `Contact` gains an optional
schedule (`start_s`, `end_s`); a contact with no schedule is always available,
so every increment-2 topology is byte-for-byte unchanged. A contact is usable at
time `t` when it is up and `t` lies in its window. Routing becomes a
contact-graph search: a Dijkstra over the time-windowed contact graph from the
bundle's current holder that minimises the bundle's earliest arrival at its
destination, honouring the current clock, each contact's window, and the
bundle's expiry. The first contact on the earliest-arrival route is the next
hop, taken only once that contact is actually open, so a bundle moves toward the
node where a future contact will open and waits there. A bundle with no feasible
route to its destination before it expires is held and re-evaluated as the clock
advances. This is the contact-graph-routing model scheduled DTN uses (the
approach ION/CGR takes), reduced to one legible earliest-arrival search rather
than a cached route list. With no schedules configured the search reduces to
earliest arrival over always-up contacts, which for uniform contacts is the
shortest path increment 2 produced; ties break by hop count then neighbour EID
so the route stays deterministic.

**An explicit custody acknowledgement.** Custody transfer is modelled as a
separately-lossy acknowledgement instead of being folded into forward success.
When a custodial bundle is forwarded successfully the receiving node accepts
custody and returns a custody signal, delivered with probability one minus a
configured acknowledgement-loss fraction (`ack_loss_pct`, default zero). When
the signal lands the previous custodian releases its copy, exactly as the folded
model did, so `ack_loss_pct = 0` reproduces ADR 0062's custody behaviour byte
for byte and consumes no RNG draw. When the signal is lost the previous
custodian retains its copy and retransmits, putting a second copy of the same
bundle into the network; the copies converge and the node-level deduplication
this increment adds (keyed on the bundle id that ADR 0061 established) delivers
the bundle once and counts the duplicate. A custodian that keeps losing
acknowledgements stops retaining once it exceeds the same retransmission bound a
lost forward uses, so the duplicate count stays bounded.

The two tools keep their shape. `dtn_send` (T2) still originates and `dtn_mesh`
(T0) still reads; the read gains a deduplication counter and reports each
contact's window alongside its up/down state.

## Consequences

A controller can now watch a bundle held at a relay for a scheduled contact and
delivered when that contact opens, and watch a guaranteed bundle survive a lost
custody acknowledgement as a deduplicated duplicate rather than a silent second
delivery. The mesh stays deterministic: the acknowledgement draw rides the same
ADR 0019 RNG seam as the forward-loss draw and is skipped entirely when
acknowledgement loss is zero, so existing seeded scenarios replay unchanged.

The cost is a per-bundle earliest-arrival search each tick, bounded by the
configured topology size, and a second representation for the transient duplicate
a lost acknowledgement creates. The mesh remains inert without a `dtn` profile
section, so the cost is opt-in. Two fidelity limits are recorded rather than
modelled: the route search respects contact windows and bundle expiry but does
not reserve transmission volume across the planning horizon (per-tick rate
budgeting handles local contention), and a contact's arrival time counts
transmission time only, not one-way light time.

## Revisit triggers

The replay increment (BL-056 increment 4) persists a node's bundle store across a
contact outage so a bundle survives a node restart, not just a link drop. Full
contact-graph volume reservation and a one-way-light-time term would land if a
scenario needs congestion-aware routing or deep-space timing fidelity. Revisit
the single-hop-per-tick rule if a fast scheduled contact should drain several
hops within its window in one tick.
