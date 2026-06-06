# ADR 0038: Self-model situational awareness

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0010 (self-model and estimation layer), ADR 0007 (additive surface rule), ADR 0022 (runtime safety enforcer)

## Context

The self-model layer (ADR 0010, BL-018, BL-035) answers "what can the device
do right now, and how confident are you?" through `self_model_assess`: three
capability claims (endurance, thermal headroom, inference capacity) carrying
Monte Carlo quantile bands. `self_estimator_status` exposes the raw estimator
state (source, last-update timestamp, covariance), and `state_get` exposes the
FSM posture. What no single read does is fuse them. A controller that wants the
whole tactical picture has to call three tools and correlate a capability claim
with the estimator that backs it, the freshness of that estimate, the device's
posture, and what to do when a claim has degraded. BL-061 is that synthesis.

The four elements BL-061 names already have their raw materials in place.
Confidence bands are the assess quantiles. Source provenance is
`Capability.drivers` (the subsystems behind a claim) plus each driving
estimator's `Estimate.source`. Staleness is the gap between the freshest
estimator clock and each estimator's `Estimate.ts_s` (measured against the
estimators, not the engine clock, so it survives a `profile_reload` that
rebuilds estimators on a fresh timebase). Degraded-mode recommendations are derivable from
the same live state the engine's own auto-safing reads (ADR 0027, ADR 0028):
the FSM mode, the operator and comms labels, the compute throttle flag, and
which capability bands have squeezed against their thresholds. The gap is a
layer that assembles them and a tool that surfaces it.

## Decision

Add `src/nous/self_model/situation.py` with a `situation(engine)` function that
returns a `Situation`: the FSM posture (mode plus the operator and comms labels
with reasons, and a one-word summary), the capability claims each enriched with
a `status` and a `provenance` list (the backing estimator's source and its
staleness in seconds), the safety enforcer's violation posture, and a short
ranked list of degraded-mode recommendations. It builds on `assess` rather than
recomputing the quantile mapping, so the headline numbers stay identical to
`self_model_assess`.

Register it as `self_model_situation`, a read-only T0 tool beside the other
self-model reads, classified in `policy.py` (the one boundary touch, an
additive frozenset entry following ADR 0031, ADR 0032, and ADR 0033). The
existing self-model tools are unchanged, so this is purely additive (ADR 0007).

Two honesty constraints shape the design. Staleness (`age_s`) is surfaced as
the literal estimator clock lag; under live ticking every estimator updates each
tick, so it sits near zero and grows only when an estimator stalls. The live
trust signal stays the covariance-derived `confidence`, and both are surfaced so
a controller can tell a stale claim from a merely uncertain one. Recommendations
are advisory heuristics ranked to mirror the engine's auto-safing priority
(operator, then power, then thermal, then comms); they are not a safety gate.
The `SafetyEnforcer` (ADR 0022) remains the only authority that refuses or
clamps, and where the engine carries a real threshold (thermal headroom) the
status reads against it rather than inventing one.

## Consequences

A controller gets the device's tactical picture from one T0 read: which
capabilities are intact, which have degraded, where each claim comes from and
how fresh it is, the current posture, and a ranked set of actions. The synthesis
is the project's thesis made legible in a single object. The tool surface grows
from thirty-six to thirty-seven; `self_model_assess` and `self_estimator_status`
are untouched, so existing callers are unaffected.

The recommendations are rule-based and advisory; a learned recommender is out of
scope (BL-046). The advisory thresholds are named constants in one module, tuned
for the reference profile's scale; a deployment with a very different battery or
thermal envelope may want to read them from the profile, which is a natural
follow-up. BL-061's old cross-references conflated this situational-awareness
layer with the position estimator's planned EKF; those are re-pointed to BL-026
(the position estimator's own id), removing the double-booking.

## Revisit triggers

Revisit if the advisory thresholds need to move into the profile YAML (a
deployment whose scale makes the fixed minutes-of-endurance bands misleading).
Revisit if a controller needs the currently-tripped safety constraints rather
than the cumulative counts, which would mean surfacing a live enforcer
evaluation rather than `posture()`. Revisit when the position EKF (BL-026)
lands, since a real velocity covariance would let the situation layer carry a
navigation capability claim alongside the three it fuses today.
