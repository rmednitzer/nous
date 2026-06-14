# ADR 0045: Estimator innovation gating and health

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0010, ADR 0019
- **Note:** Renumbered from 0042 to resolve a filename collision with `0042-confine-scenario-load-to-a-directory`; the originating commit references the former number.

## Context

The estimators from ADR 0010 shipped as per-channel scalar Kalman filters
that exposed only a mean and a variance. That is enough to smooth a sensor
but not enough to be honest. A controller reading `self_estimator_status`
could not tell a filter that had just rejected a wild reading from one that
was merely uncertain, and the tool advertised "divergence flags" it never
actually produced. Worse, the position filter reported a lat/lon variance of
exactly zero once it converged: a noiseless one-step collapse that claimed
perfect certainty the sensor could never support.

An audit comparing `nous` to PX4-Autopilot put the gap in focus. PX4's EKF2
treats a filter as something that must describe its own fitness: it gates
each measurement on a normalised innovation squared (NIS) test ratio, tracks
per-source health and fault flags, counts state and covariance resets, and
floors and repairs its covariance rather than letting it collapse or diverge.
The `nous` self-model already produces a more sophisticated output than PX4
(calibrated p5/p50/p95 capability bands), but the estimators feeding it were
less rigorous than EKF2. The point of this change is to make the filters
worthy of the legibility layer that consumes them.

## Decision

A shared primitive, `ScalarChannel` in `src/nous/estimators/health.py`,
centralises the per-channel recursion every scalar estimator open-coded, and
adds the diagnostics a self-describing estimator needs. Each channel now:

1. Gates a measurement on `test_ratio = innovation^2 / (gate_sigma^2 * S)`,
   rejecting it when the ratio exceeds one or is non-finite (the NIS gate).
2. Maintains a signed, exponentially weighted test ratio, so a persistently
   biased sensor is visible (and its direction legible) before it ever trips
   the hard gate.
3. Floors its posterior variance, so a converged belief stays honest about
   residual sensor noise instead of collapsing to a false-certainty zero.
4. Adopts a *sustained* disagreement through a counted reset after
   `reset_after` consecutive rejections, rather than fighting a genuine jump
   forever. A single outlier is rejected; a real shift is taken.
5. Seeds itself on its first fusion: the gate is skipped until the channel
   holds a belief, exactly as an EKF initialises from its first fix.

`Estimate` gains an optional `EstimatorHealth` block (`healthy`, `fused`,
`dead_reckoning`, `rejected_updates`, `reset_count`, and the per-channel
`test_ratio`, `test_ratio_filtered`, and `innovation`), which
`self_estimator_status` now serialises. The `Estimator` Protocol
(`predict` / `update` / `state`) is unchanged: health rides inside the
`Estimate` returned by `state`, so the contract in `estimators/base.py` is
untouched and every consumer that reads only `point` and `covariance` keeps
working. The comms particle filter reports a compatible block built from
particle-weight collapse, the non-Gaussian analog of a covariance reset.

## Consequences

Easier: the self-model's capability bands are now fed by filters that reject
implausible readings instead of folding them in at full gain, and a
controller can finally distinguish a stale, coasting, rejecting, or diverging
filter from a healthy one. The scenario and injection surface is hardened, a
plausible-but-in-range spoofed value no longer poisons the estimate, and the
position filter reports a GNSS-realistic floor with a `dead_reckoning` flag
when it is coasting without a fix.

Harder: each estimator now carries per-channel tuning (gate width, variance
floor, reset threshold), and a legitimately sustained step is adopted with up
to `reset_after` updates of lag rather than instantly. The filters remain
diagonal and scalar, with no cross-covariance, and most process models still
inflate variance rather than integrating dynamics. Those are deliberately the
next steps, not this one.

## Revisit triggers

- Cross-covariance or matrix-valued filters land (the BL-027 power EKF, the
  BL-028 thermal RC model, or a coupled position filter). At that point the
  scalar variance floor must become covariance repair: force symmetry after
  prediction and reduce an over-large variance through a zero-innovation
  fusion step rather than clamping the diagonal, following EKF2.
- Telemetry from a real device introduces measurement latency, at which point
  a delayed-time-horizon buffer (per-sensor, timestamp-indexed) replaces the
  current snap-the-clock-to-the-observation model.
- A subsystem's sustained-step adoption proves too slow at `reset_after`, and
  a per-channel fast path or a wider gate is warranted.
