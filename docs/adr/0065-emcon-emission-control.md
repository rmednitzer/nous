# ADR 0065: EMCON emission-control postures

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0007, ADR 0033, ADR 0047

## Context

The twin models communication paths in depth (link budgets, store-and-forward
triage, a DTN overlay), but every path assumes the device emits whenever a link
can carry the bytes. An edge appliance under OPSEC discipline does the opposite:
it controls its emissions (EMCON), going silent or restricting to a
low-probability-of-intercept channel even when links are healthy, to avoid being
detected or located. BL-060 adds that emission-control layer. This is the "comms
deliberately unavailable" side of the standing comms-paths work, and it pairs
with the BL-056 triage layer: a silenced device must hold its outbound traffic,
not drop it.

The opportunity is that the comms subsystem already funnels every outbound byte
through a single seam, `CommsSubsystem.tx`, which returns zero to mean "not
sent". A gate placed there controls emissions uniformly and, because the BL-077
outbox already defers a package whose `tx` returns zero, buys the
store-and-forward tie-in without new plumbing.

## Decision

EMCON is modelled as an orthogonal, operator-imposed posture, the same shape as
`operator_state` and `comms_state`: a set of named emission profiles, each
listing the comms links permitted to emit, with one active at a time. Two
profiles are always present, `unrestricted` (every link) and `silent` (none),
and further named profiles come from an optional `comms.emcon` profile section,
so a profile without one leaves EMCON unrestricted and inert. The posture lives
on the comms subsystem, is read by `emcon_status` (T0), and is changed by
`emcon_set` (T2).

The gate sits at `CommsSubsystem.tx`, the one point every outbound byte funnels
through (direct sends, interop publishes, the outbox flush). When the active
profile forbids emitting on a link, `tx` returns zero, the same contract a
forced-down or zero-capacity link already uses. That single placement carries the
store-and-forward tie-in: the BL-077 outbox flush already re-queues any package
whose `tx` returns zero and re-attempts every tick, so a silenced device's
backlog drains automatically once the posture is lifted.

EMCON is kept distinct from `CommsState`. `CommsState` stays a link-health label,
so the audit and the controller can tell "the operator silenced us" from "the
link is physically dead": an EMCON-silenced device still reports its links
healthy, with the suppression visible through `emcon_status`. The fire-and-forget
send tools close the loop with triage: when EMCON forbids a link, `comms_send`,
`comms_publish`, and `self_model_publish` hold the message in the outbox (tagged
`emcon_deferred`) rather than dropping it, so guaranteed traffic survives the
silent window. This is deliberately not part of `policy.py`: the T0-T3 tool-tier
admission system is a separate concern, and EMCON is an emission gate the comms
layer owns. Posture changes (`emcon_set`) and the affected emission calls ride
the existing audit path; a first-class denial flag on the audit record would
extend the high-blast audit surface and is deferred.

## Consequences

A controller can impose radio silence or a low-probability-of-intercept profile
and watch the device hold its outbound packages until emissions resume, closing
the loop between the comms-denial side and the BL-056 triage side. The cost is
one membership check in the hot `tx` path (negligible) and a new orthogonal
posture to reason about. The layer is inert without a `comms.emcon` section and
under the default `unrestricted` profile, so every existing profile and test is
unchanged; the spot-core profile ships a demonstrative `low_pi` profile.

Two limits this increment records. EMCON here is an emission gate, not a
metadata-minimisation or burst-window model (those are later BL-060 increments),
and the posture is in-memory, resetting to the profile default on a process
restart or hot reload (unlike the DTN store, it is not persisted). The one
safety-adjacent interaction, a silenced device that still reports comms healthy,
is surfaced through `emcon_status` and left for a future STPA pass if it proves
to be a control hazard rather than purely an OPSEC feature.

## Revisit triggers

Metadata minimisation and burst or scheduled-emission windows are the next BL-060
increments. A first-class `denied` audit record carrying EMCON context (touching
the audit and runner surfaces) lands if the OPSEC posture needs explicit denial
provenance beyond the current audited call trail. Persisting the active posture
across a restart would follow the ADR 0064 pattern if an operator-set silence
must survive a reboot.
