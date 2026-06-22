# ADR 0084: imu_status read tool

- **Status:** Accepted
- **Date:** 2026-06-22
- **Authors:** rmednitzer
- **Builds on:** ADR 0007, ADR 0019, ADR 0021, ADR 0073, ADR 0076

## Context

The IMU subsystem (`subsystems/imu.py`) shipped with the GNSS/INS fusion work
(ADR 0073, ADR 0076): a body-frame longitudinal accelerometer and a yaw-rate
gyro derived from the platform motion, each carrying a slowly drifting bias the
position EKF estimates as part of its error state. The subsystem is wired
through the engine tick and drives the EKF prediction, but it is the only
modelled subsystem with no read tool on the registered surface. A controller
can see the EKF's inferred biases through `position_status`, but not the
inertial truth, the true biases the filter is chasing, or the measurement noise
envelope. BL-026 left an `imu_status` tool as its last open increment,
deferring the `policy.py` classification to this ADR.

The tier classifier defaults an unclassified tool to `STATEFUL` (ADR 0007's
additive-surface rule), so a pure read registered without a classification
would be wrongly refused under readonly and guarded modes. Adding a name to a
tier frozenset touches `policy.py`, a high-blast surface, so the classification
is recorded here.

## Decision

Register `imu_status` as a T0 (read-only) telemetry tool in
`tools/subsystems.py`, beside `position_status`, and add the name to
`policy.py`'s `_READ_ONLY_TOOLS` set. It is a uniform truth-plus-estimate read
like the other subsystem status tools, so it lives in the same module (ADR
0021's capability-grouping).

The payload reports the inertial truth (along-track acceleration, yaw rate),
the two true sensor biases that corrupt the raw signal, and the white-noise
standard deviations that bound the measurement. Because the IMU has no
estimator of its own, the `estimate` block reads the position EKF's inferred
accelerometer and gyro biases with one-sigma bounds (ADR 0076), so a controller
can compare the filter's belief against the truth and see how far the
bias estimate has converged. Two read-only `accel_sigma` / `gyro_sigma`
properties are added to the subsystem so the tool can surface the noise
envelope.

The tool reads `truth()` and the EKF `state()` only, never `sensor_obs()`. The
observation path draws accelerometer and gyro white noise from the engine RNG,
so calling it from a tool would advance the shared RNG stream and break the
simulation's seeded determinism (ADR 0019). `position_status` already follows
this discipline, reading truth and the estimator rather than the observation;
`imu_status` matches it.

## Consequences

Every modelled subsystem now has a registered read, so the IMU is as legible as
the rest of the platform: a controller reads the inertial signal, the bias
corrupting it, and the filter's estimate of that bias in one call, and the
GNSS/INS bias-estimation story (ADR 0076) becomes observable from the tool
surface rather than only from `position_status`'s estimate block. The tool
surface grows by one T0 read; the classification is additive and the engine,
the IMU subsystem, and the EKF are otherwise untouched.

The cost is a small one: the read surfaces a second view of the EKF bias
estimate that `position_status` already exposes, accepted because the IMU read
frames it against the inertial truth and the noise envelope, which
`position_status` does not carry. There is no separate IMU estimator, so the
`estimate` block is borrowed from the position filter rather than produced by a
dedicated one; if the IMU ever grows its own pre-fusion estimator, the block
moves to it without changing the tool's shape.

## Alternatives considered and rejected

- Fold the inertial truth into `position_status` instead of a new tool.
  Rejected: it would overload a tool already dense with the navigation solution,
  and the IMU is a distinct subsystem the controller may want to read on its
  own; the uniform one-tool-per-subsystem read is more legible.
- Surface the measured observation (truth plus bias plus noise) directly.
  Rejected: computing it requires drawing from the engine RNG, which would break
  the ADR 0019 determinism; the truth, the biases, and the noise sigmas together
  let a controller reconstruct the observation envelope without perturbing the
  stream.
- Leave the IMU unexposed. Rejected: it is the only subsystem with no read, and
  the bias-estimation behaviour it drives is exactly the kind of internal state
  the twin exists to make legible.

## Revisit triggers

- The IMU grows a dedicated pre-fusion estimator (then the `estimate` block
  reads it rather than the position EKF).
- A multi-IMU or higher-DoF inertial model lands (then the payload grows the
  additional channels under the ADR 0012 additive rule).
