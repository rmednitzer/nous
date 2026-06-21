# ADR 0076: Error-state IMU bias estimation in the position EKF

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0073, ADR 0019, ADR 0045

## Context

ADR 0073 landed the nonlinear position EKF with a four-element state
`[e, n, v, psi]` and named its own first revisit trigger: the IMU bias was not
estimated, so a fixed accelerometer or gyro bias drifted the dead-reckoned coast
during a GNSS outage. That is the realistic, visible behaviour of a strapdown
solution with no bias observer, but it is also the single most valuable thing an
INS/GNSS filter does that the four-state filter did not: a real autopilot
(PX4 EKF2, ArduPilot) carries the inertial-sensor biases as states precisely so
the inertial solution it coasts on is the de-biased one.

The IMU subsystem (ADR 0073) already separates truth from the biased measurement:
the accelerometer reads the true specific force plus a bias random walk plus white
noise, and `truth()` carries the bias separately. So the scoring target for a
bias-estimating filter already exists; what was missing was the estimator state to
recover it.

## Decision

Augment `PositionEkf` from four states to six: `[e, n, v, psi, b_a, b_omega]`,
where `b_a` is the accelerometer bias (m/s^2) and `b_omega` the yaw-rate gyro bias
(rad/s). The two bias states are modelled as a slow random walk (constant in the
mean, a small process-noise variance per second), the standard error-state
treatment.

`predict` subtracts the estimated bias before integrating the IMU control:
`a_corr = accel - b_a` drives the speed and `omega_corr = yaw_rate - b_omega`
drives the heading, while the bias states carry forward unchanged. The Jacobian
gains two columns: the speed row picks up `-dt` against `b_a` and the heading row
`-dt` against `b_omega`, so the covariance propagation couples the biases into the
states they corrupt. A constant bias then accumulates a position error (quadratic
in time for the accel bias, motion-dependent for the gyro bias) that GNSS observes,
so the biases are recovered through the same cross-covariance that already recovers
speed and heading: no new measurement, just two more observable error states. The
biases stay observable only under motion and a position fix, exactly as the real
INS/GNSS observability story requires.

The measurement, gate, re-anchor, and altitude paths are unchanged in form: the
GNSS measurement matrix gains two zero columns (GNSS sees position, not bias), and
the re-anchor reset leaves the bias states untouched because a teleport changes the
device's position, not its inertial-sensor bias. `state()` surfaces `accel_bias_mps2`
and `gyro_bias_rps` with their variances additively beside the existing keys, and
`position_status` now reports the inferred speed, heading, and both bias estimates
with one-sigma bounds so the new capability is legible to a controller.

The `predict / update / state` Protocol (`estimators/base.py`) is untouched, the
profile schema is untouched, and the engine wiring is untouched: the augmentation is
internal to the filter. A profile with no new configuration behaves as before; the
bias states simply start at zero with a wide prior and converge if the motion and
fixes excite them.

## Consequences

Under a GNSS outage the EKF now coasts on the de-biased inertial solution: once the
bias has converged, the prediction holds the true speed and heading rather than
integrating the raw biased IMU into a runaway drift. The regression test pins the
value directly: over a 20 s coast a converged accel-bias filter tracks the truth to
better than a quarter of the ~60 m drift the same bias would produce if it rode raw.
This closes the named work in ADR 0073 and BL-026; LIMITATIONS L13 is updated from
"no online IMU-bias estimation" to record that the position filter now estimates the
inertial biases while the remaining estimators stay linear-Gaussian.

The cost is a six-by-six covariance propagation in `predict` (still trivial at the
tick budget) and a slower transient: the biases are observable only through double
integration, so they converge over tens of seconds of motion, not instantly. The
wide bias prior means an unexcited filter (stationary, or no fix) leaves the biases
near zero with high variance rather than committing to a wrong value, which is the
honest posture.

`PositionKalman` remains retired-in-place (ADR 0073) and is unaffected. No new tool
ships, so the policy classification is untouched; the bias estimates flow through the
existing `position_status` T0 read.

## Alternatives considered and rejected

- A full 15-state error-state INS (attitude quaternion, three-axis accel and gyro
  biases). Rejected as before (ADR 0073): the planar twin carries one longitudinal
  accelerometer and one yaw gyro, so two scalar bias states are the matching
  error-state extension, not a six-axis IMU model.
- Estimating only the accelerometer bias. Rejected: the gyro bias is the one that
  walks the heading and so the coast direction, and it costs one more state to carry;
  omitting it would leave the more dangerous drift unobserved.
- A separate bias-calibration routine run offline rather than online states.
  Rejected: it would not track a bias that drifts in flight and would not compose with
  the existing recursive filter, the whole point of an error-state formulation.
- Resetting the bias states on a re-anchor. Rejected: a teleport or re-acquired fix is
  a position discontinuity, not a sensor event, so the bias estimate is still valid and
  resetting it would throw away hard-won convergence.

## Revisit triggers

- The platform gains lateral or vertical dynamics the planar two-bias model cannot
  represent (then the state grows toward the full error-state INS).
- A bias is observed to drift faster than the random-walk process noise tracks (then
  the `Q` for the bias states is retuned, or a scale-factor state is added).
- A controller needs the raw IMU bias surface independently of position (then
  `imu_status` lands with its policy classification, still deferred from ADR 0073).
