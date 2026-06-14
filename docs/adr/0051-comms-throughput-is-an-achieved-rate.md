# ADR 0051: Comms link throughput is an achieved rate, not a packet size

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer

## Context

`CommsSubsystem.tx` recorded a transmission by setting `link.throughput_bps =
n_bytes * 8`, the bit count of the single packet, on a field named and consumed
as a rate (bits per second). The 2026-06-14 audit (COMMS-3) flagged the
mislabel: `comms_state.derive` gates a link as healthy on `throughput_bps >
5000`, and the comms particle filter reads the same field as the observed
throughput, so a one-off large packet read as healthy and a small packet read as
degraded regardless of the rate at which the link was actually carrying data.
The fix was deferred from the additive cadence pass because correcting it changes
the input signal those two consumers see.

The change is contained by a quirk of the estimator: `CommsParticleFilter.update`
sets `expected_throughput_bps = max(observed, floor)`, so the log-throughput
residual is self-referential and contributes nothing to the likelihood. The
estimator is therefore insensitive to the throughput scale (it uses the value
only through the live-throughput floor gate), which leaves `comms_state.derive`
as the dominant consumer of the magnitude, and `comms_state` is the FSM-facing
label that gates the inference-fallback ladder.

## Decision

`throughput_bps` becomes an achieved rate: the bits transmitted divided by the
interval since the link last sent (`link.age_s`, which the same `tx` call then
resets to zero), capped at the link's `bandwidth_bps` because a transmission
cannot beat the link's capacity. When no time has elapsed (the first send after
construction, or two sends inside one instant) the rate is reported as the link
bandwidth rather than dividing by zero.

The flat `comms_state` threshold of 5000 bps is unchanged, but it now compares
against a genuine rate, so it distinguishes a link carrying meaningful traffic
from an idle or slow one rather than a large packet from a small one. Degradation
injected through `set_link_state` (an explicit `throughput_bps`, an elevated
`loss_pct`) is unchanged, since that path does not go through `tx`.

## Consequences

The comms model gains a real bound: `throughput_bps` is now at most the link
bandwidth, a property the bit-count never respected, and the value a controller
reads from `comms_status` is a rate it can reason about against the link's
nominal capacity. A link the controller transmits on infrequently reads as a
lower throughput, which is the honest meaning of a rate; a scenario that wants to
model link degradation independent of send cadence should set `throughput_bps`
or `loss_pct` directly rather than lean on packet size.

No existing test pinned the old bit-count (the throughput-zero invariants drive
`set_link_state`, not `tx`), so none broke; new unit tests pin the rate over the
send interval, the bandwidth cap, and the first-send fallback. The estimator's
convergence tests are unaffected because they build observations with explicit
throughput values and because the filter is scale-insensitive by construction.

Alternatives rejected. Computing the rate over the transmission time
(`bits / bandwidth`) collapses to the bandwidth on every send, erasing all
signal. Keeping the bit count and renaming the field does not help, because the
two consumers want a rate, not a packet size, so the rename would only push the
mislabel downstream. Leaving it as is keeps a mislabeled quantity feeding the FSM
gate, which is the defect the audit recorded.

## Revisit triggers

- The SNR-to-throughput propagation model (BL-041 / BL-048) lands and derives
  throughput from link physics (RSSI, loss, modulation) rather than send cadence,
  superseding the inter-transmission-interval rate here.
- The 5000 bps health threshold needs to scale per link (a fraction of each
  link's bandwidth) rather than a single flat value across a heterogeneous link
  inventory.
