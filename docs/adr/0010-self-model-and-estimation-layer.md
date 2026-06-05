# ADR 0010: Self-model and estimation layer

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001, ADR 0006

## Context

A controller using `nous` is most useful when it can make calibrated
claims: "the unit has 47 minutes of endurance under the current load,
5C of thermal headroom, and 200 tok/s of inference capacity". Bare
sensor readings cannot answer such a question; the self-model needs a
filtered belief about each subsystem and then a layer that turns those
beliefs into capability quantiles.

## Decision

Two layers:

1. **Estimators** (`src/nous/estimators/`). One per subsystem. Each
   implements the `Estimator` Protocol (`predict / update / state`).
   The simplest filter that meets the model card's covariance bound is
   the right choice; v0.1 uses Kalman and particle filters as
   needed (EKF / UKF remain on the menu for the nonlinear couplings
   tracked in the backlog, but no v0.1 estimator needs one yet).
   Linear-Gaussian assumptions are explicit in
   `LIMITATIONS.md` L13.
2. **Self-model** (`src/nous/self_model/`). The `assess` function reads
   estimator state and produces an `Assessment` with calibrated
   quantiles (p5/p50/p95) for endurance, thermal headroom, inference
   capacity, and any extras. `explain` renders an `Assessment` as a
   readable summary. `viability` answers feasibility questions for a
   proposed task.

The self-model is *parametric*, not learned (see `LIMITATIONS.md` L14).
The rules live in code so they can be reviewed and tested. Model cards
under `docs/model-cards/` document each estimator's inputs, outputs,
covariance bound, and known failure modes.

## Consequences

Easier: capability claims have a single home and a single calibration
method. The controller does not need to do its own statistics.

Harder: every subsystem must produce sensor observations with a
calibrated noise model. The covariance bounds in the model cards are a
contract.

## Revisit triggers

- Heavy-tailed disturbances make the Gaussian assumption indefensible
  for a subsystem; switch to a particle filter and update the model
  card.
- A learned self-model becomes desirable (post-1.0, BL-046).
