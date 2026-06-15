# ADR 0062: Multi-node DTN mesh with custody transfer

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0047, ADR 0061

## Context

ADR 0061 gave the device's outbox a BPv7 bundle identity, the first increment of
the delay-tolerant-networking layer (BL-056). The BL-077 outbox is single-hop:
it holds the device's own transmissions for its direct radios and flushes them as
those links recover. The remaining DTN vision is a network, not a single egress
buffer: bundles that traverse several nodes toward a remote endpoint, stored and
forwarded at each hop, with custody transfer for reliability across intermittent
contacts. Modelling that needs more than one node.

The decision recorded here is how a single-device twin hosts a multi-node mesh
without becoming a general network simulator: the `nous` device is one node in a
configured topology of otherwise-abstract peers, and the mesh is a deterministic
overlay the engine steps each tick.

## Decision

A new `state/dtn_mesh.py` models the mesh. A `DtnNode` is an endpoint identifier
plus a store of the bundles it currently holds; the device is the `self` node and
peer nodes are abstract hold-and-forward stores with no subsystem physics, the
same way BL-048 models a link's far peer as a position rather than a second
device. A `Contact` is an edge between two node EIDs carrying an up/down state, a
rate, and a loss fraction. The topology (the peer EIDs and the inter-node
contacts) is a new optional `dtn` profile section, so a profile without it leaves
the mesh empty and inert and every existing profile is unchanged.

`DtnMesh.step` runs each tick after comms (ADR 0019 clock and RNG seams, so a
seeded run is reproducible). It expires bundles past their lifetime, then walks
each node's held bundles in the same precedence-then-age triage order the outbox
uses (ADR 0047) and routes each at most one hop toward its destination over the
shortest path on the currently-up contact subgraph, rate-limited by the contact's
per-tick byte budget. A bundle with no up-path stays put (store-and-forward); a
bundle that reaches its destination node is delivered.

Custody transfer is the reliability distinction. A bundle marked custodial is
retained by its current custodian until a forward succeeds; a lost forward (a
draw against the contact loss, the same Bernoulli model the outbox flush uses)
keeps the bundle and counts a retransmission, and the bundle is dropped only when
it exceeds a configured retransmission bound. A best-effort bundle is forwarded
once and dropped on a lost forward. For this increment the custody acknowledgement
is folded into forward success rather than modelled as a separate, separately-lossy
return path; the duplicate a lost ack would create (and the receiver-side dedup
that ADR 0061 already enables) is deferred to the routing increment. Two new
tools expose the layer: `dtn_mesh` (T0) reads the topology, the per-node bundle
counts, and the disposition counters, and `dtn_send` (T2) originates a bundle at
the device node toward a destination EID.

## Consequences

A controller can now watch a situation report travel from the device across a
relay chain to a ground endpoint, see it held when a contact drops, and tell a
custodial (guaranteed, retransmitted) bundle from a best-effort one. The mesh is
a distinct concern from the BL-077 outbox: the outbox is the device's direct-link
egress, the mesh is the DTN overlay, and a later increment may bridge them (the
self-node's contacts driven by the live link states). The cost is a second bundle
representation and a per-tick routing pass bounded by the configured topology
size; the mesh is inert without a `dtn` profile section, so the cost is opt-in.
The folded custody acknowledgement and the hop-count routing metric are
deliberate simplifications this increment records and the next two revisit.

## Revisit triggers

The routing increment replaces hop-count shortest path with an intermittent-contact
policy (epidemic, spray-and-wait, or contact-graph routing) and models the lossy
custody acknowledgement and its duplicate explicitly; the replay increment
persists a node's bundle store across a contact outage. Revisit the single-hop-per-tick
rule if a fast contact chain should drain a bundle several hops in one tick.
