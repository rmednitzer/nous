# Conformance posture: DTN (RFC 4838) and Bundle Protocol v7 (RFC 9171)

**Module:** `src/nous/state/dtn_mesh.py` (mesh, contact-graph routing,
custody, persistence) and `src/nous/state/comms_outbox.py` (the BPv7-shaped
bundle identity on the device's own queue). Tools: `dtn_send` (T2),
`dtn_mesh` (T0).

**Standard:** RFC 4838 is the delay-tolerant-networking architecture
(store-carry-forward over intermittent links, custody transfer, late
binding of endpoint identifiers). BPv7 (RFC 9171) is the Bundle Protocol
version 7 message model. Schedule-aware contact-graph routing follows the
CGR / CCSDS SABR idea of routing over a time-windowed contact plan.

**Current posture:** The DTN layer is a *behavioural* simulation of a BPv7
bundle mesh, not a wire-format implementation (BL-056, ADRs 0061-0064).
Every package carries a bundle identity modelled on the BPv7 primary
block: a source endpoint identifier (the device node EID,
`dtn://<profile>/` by default), a destination EID (`dtn://controller/` by
default), a creation timestamp (the simulated enqueue clock, ADR 0019), a
creation sequence, and a canonical `bundle_id`; the TTL is the bundle
lifetime. A multi-node mesh of abstract hold-and-forward peers, connected
by scheduled contacts from the profile `dtn` section, is stepped each
tick: `dtn_send` originates a bundle that contact-graph routing moves one
hop per tick along the earliest-arrival path still meeting the deadline,
storing it at a node while a contact is down. Custody transfer retains and
retransmits a custodial bundle on a lost forward or a lost custody
acknowledgement (Bernoulli draws on the contact, ADR 0019 RNG seam) up to
a retry bound, deduplicating per node on the bundle id; a best-effort
bundle is dropped on loss, and a bundle past its lifetime expires. The
whole store (held bundles, dedup ledgers, counters, sequence) is
checkpointed to SQLite and restored on a fresh mesh, so a custodial bundle
survives a process restart, with lifetimes rebased to their remaining TTL
across the clock reset.

**What is supported:** The DTN *behaviour* RFC 4838 describes
(store-carry-forward, custody transfer with retransmission, dedup,
schedule-aware routing, replay on reconnect) and a BPv7-shaped bundle
identity with `dtn:`-scheme EIDs and an explicit lifetime.

**What is omitted:** The BPv7 *wire format*. There is no CBOR-encoded
bundle, no canonical block structure on a wire, no BPSec (RFC 9172)
security blocks, no convergence-layer adapters (TCPCL / UDPCL), and no
real CGR contact-plan (SABR) ingest. Custody transfer follows the classic
BPv6 (RFC 5050) custody concept, which BPv7 moved out of the core; the EID
is a `dtn:`-shaped string label, not a routed CBHE-encoded address. Mesh
nodes and contacts are abstract, with inter-node loss as a Bernoulli draw
rather than the propagation link budget the device's own comms links carry.

**Conformance claim:** None. This is a documented behavioural model of DTN
and BPv7 semantics for a simulated mesh, not a certified RFC 9171
implementation, and it is not interoperable with a real BPv7 stack on the
wire.

**Tracking:** BL-056 (done); custody-store bound and restore-loss
accounting in BL-098 / BL-100 (done, ADR 0068). Per-cause drop diagnostics
are BL-108 (planned).
