# ADR 0053: Propagation-aware comms link quality

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer

## Context

A comms link's live `rssi_dbm` and `loss_pct` sat at the profile's static
nominal forever: quality did not depend on where the device was, how far the
peer was, or what the terrain did. Three earlier decisions deferred the physics
that would change that. ADR 0020 left "throughput is monotone in SNR" as a
placeholder pending BL-048. ADR 0051 made `tx` throughput an achieved rate but
flagged two open triggers: the SNR-to-throughput coupling, and a per-link health
threshold to replace the flat 5000 bps in `comms_state.derive`. ADR 0047 noted
that once a link is lossy the store-and-forward flush needs to model partial
delivery rather than all-or-nothing. BL-048 closes all of these in one model.

The risk is blast radius: a naive rewrite touches the subsystem, the estimator,
the typed `LinkEstimate` boundary, the FSM-facing `derive`, and the outbox at
once, churning the comms, estimator, and outbox test suites. The model is
designed so that does not happen.

## Decision

The propagation model is an opt-in, additive layer. Every new channel is
optional with a legacy fallback, so the model is inert until a profile declares
it, and a link with no propagation block reproduces today's behaviour exactly.

1. **Link budget.** A link may carry a `propagation` block (peer lat/lon/alt,
   transmit power, frequency, antenna gains, a constant excess/terrain loss, a
   log-normal shadowing sigma, a receiver noise floor, the SNR ramp endpoints,
   and an RSSI-to-loss curve). When present, each tick the subsystem computes
   the slant range from the device position to the peer, the Friis free-space
   path loss, draws log-normal shadowing from the engine RNG (ADR 0019), and
   sets the link's live `rssi_dbm` and `loss_pct` from the received power.
   Device position enters through a lazy `position_fn` seam that mirrors the
   `rng=` injection.

2. **Capacity.** Each link exposes `capacity_bps`, the SNR-derived sustainable
   rate: `bandwidth_bps` derated by an adaptive-modulation fraction that ramps
   from zero at an SNR floor to one at a full-rate SNR. A link with no
   propagation block has `capacity_bps == bandwidth_bps` (its rated capacity),
   so the coupling is inert without config.

3. **Throughput (supersedes the ADR 0051 cap).** `tx` caps the achieved rate at
   `capacity_bps` rather than `bandwidth_bps`. For a static link the two are
   equal, so the ADR 0051 rate is unchanged; for a propagation link a poor
   channel lowers the ceiling, which is how ADR 0020's "throughput monotone in
   SNR" is realized.

4. **Health threshold (closes ADR 0051 trigger 2).** `derive` gates a link
   healthy on a per-link rate, `capacity_bps` above a fraction of that link's
   own bandwidth, rather than the single flat 5000 bps. `LinkEstimate` gains
   optional `bandwidth_bps` and `capacity_bps`; when a caller omits them (a bare
   test fixture) `derive` falls back to the legacy flat 5000 bps on throughput,
   so the typed boundary is additive.

5. **Estimator (the deliberate scale-sensitivity change).** The comms particle
   filter's expected throughput becomes the link's modeled `capacity_bps`,
   carried on the observation, instead of the self-referential
   `max(observed, floor)`. Observed throughput far below capacity now lowers the
   connected likelihood, the scale sensitivity ADR 0051 recorded as absent.
   Absent a capacity channel the filter keeps the floor fallback, so
   manually-built observations are unaffected.

6. **Outbox (amends ADR 0047).** The flush models per-link packet loss: on a
   link with a positive `loss_pct` and an injected RNG, a package delivery can
   fail its Bernoulli draw and stay queued (its `attempts` incremented), with
   the link closing for the rest of that flush so the precedence order still
   holds. Without an RNG the flush stays all-or-nothing, so the existing outbox
   behaviour is unchanged.

The forced-state override and the `inject_comms_loss` / `set_link_state` seam
still hard-override the physics, so a scenario can pin a link regardless of the
modeled channel.

## Consequences

Link quality becomes a function of geometry. A device that drives away from its
peer watches RSSI fall, loss rise, capacity shrink, and `comms_state` degrade
then deny, all through the unchanged observation to filter to `derive` to FSM
pipeline. The model is legible: `comms_status` surfaces the range, path loss,
SNR, and capacity behind the quality, so a controller can see why a link
degraded, not just that it did.

The static-capacity-equals-bandwidth default keeps every existing comms,
estimator, outbox, and scenario test green. The new physics is exercised by a
dedicated `profiles/propagation-demo.yaml` and its integration test, by unit
tests for the link-budget functions, and by a strengthened SNR-monotone property
that replaces the placeholder in `test_subsystem_invariants`. The per-tick
link-budget math runs only for propagation links and is a handful of float
operations, so there is no measurable tick-budget impact on the static reference
profile.

Alternatives rejected. A Shannon-capacity model keyed on an RF channel bandwidth
in hertz was rejected because the profile carries a data-rate bandwidth in bits
per second, not an RF bandwidth, so an adaptive-modulation derate of the rated
rate is the honest mapping without inventing a channel bandwidth. A hard range
cliff (a link is simply in or out of range) was rejected because it loses the
graded degradation that makes the twin legible to a controller.

## Revisit triggers

- Higher-fidelity propagation is the next horizon (BL-088): terrain raytracing
  and diffraction, multipath beyond log-normal shadowing, frequency-selective
  fading, and mesh or multi-hop routing. This increment is a first-order link
  budget.
- The noise floor and the antenna gains are per-link constants. A thermal-noise
  model (`kTB` plus a noise figure) or an antenna pattern keyed on the bearing
  to the peer would replace those constants.
