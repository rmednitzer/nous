# ADR 0073: Nonlinear position EKF with GNSS/INS fusion

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0045

## Context

The v0.1 position filter (`PositionKalman`, BL-010 / BL-026) kept its state in
degrees, which made the constant-velocity process and the direct GNSS measurement
both linear. Its own docstring and BL-026 flagged the gap: a genuine EKF only earns
its name once the state carries body-frame velocity in m/s or a range / bearing
measurement, either of which couples the axes nonlinearly. The simulator also had
no real IMU: the position subsystem carried a `set_imu_drift` knob but no sensor
producing accelerometer or gyro observations, so there was nothing to fuse.

The moving-platform deepening needs both: a strapdown IMU and a nonlinear filter
that fuses it with GNSS, the GNSS/INS architecture every real autopilot (PX4 EKF2,
ArduPilot) runs.

## Decision

Add an IMU subsystem and a nonlinear Extended Kalman Filter, and swap the engine's
position estimator to the EKF.

`subsystems/imu.py` (`ImuSubsystem`) models a body-frame longitudinal accelerometer
and a yaw-rate gyro, derived by differentiating the platform's commanded speed and
heading (fed each tick from the position subsystem). The measured observation is the
truth plus a bias random walk (the ADR 0019 RNG seam) plus white noise, the standard
IMU error model; the truth carries the bias separately so a bias-estimating filter
can be scored against it.

`estimators/position_ekf.py` (`PositionEkf`) holds the state `[e, n, v, psi]` in a
local east-north-up tangent frame anchored on the first fix: east / north in metres,
ground speed in m/s, heading in radians (clockwise from north, matching the position
subsystem). The IMU drives `predict` as the control (accel integrates into speed,
yaw rate into heading); the process is the unicycle model `de = v sin(psi) dt`,
`dn = v cos(psi) dt`, nonlinear in psi, so `predict` propagates the covariance
through the analytic Jacobian. GNSS corrects east / north through a linear
measurement; speed and heading are recovered through the cross-covariance the motion
builds up, the observability that earns the EKF its name. A chi-square gate rejects
an outlier fix; a sustained jump (a teleport, a re-acquired fix far from the anchor)
is adopted through a re-anchor reset, the same persist-then-reset discipline the
scalar channels use (ADR 0045). Altitude stays a decoupled scalar channel.

The estimator satisfies the unchanged `predict / update / state` Protocol
(`estimators/base.py` is untouched): the IMU arrives as an `update` whose
`obs.source == "imu"` stores the control, GNSS as the position update, so the engine
wires it as `update(imu) -> predict -> update(gnss)` each tick. `state()` reports
lat / lon / alt (converted back from ENU) plus new speed / heading / ENU velocity
fields; the old degrees-per-second velocity keys had no consumer and are dropped, so
the change is additive for every reader (`position_status` reads only lat / lon / alt
and the health block).

## Consequences

The position estimate is now nonlinear and IMU-fused: under a GNSS outage the EKF
coasts on the inferred velocity and heading rather than freezing or drifting on a raw
velocity guess, so the dead-reckoned solution tracks a moving platform, and the
covariance and `dead_reckoning` health surface the growing uncertainty honestly.
This breaks the position half of LIMITATIONS L13 (the remaining estimators stay
linear-Gaussian). The IMU bias is not estimated this increment, so a fixed bias
drifts the coast, which is the realistic, visible behaviour; error-state bias
estimation is the follow-on.

`PositionKalman` is retained (its unit tests still pin the degrees-space filter) but
is no longer wired into the engine; `PositionEkf` supersedes it there. No new tool
ships, so the policy classification is untouched: the EKF's improved estimate flows
through the existing `position_status`.

## Alternatives considered and rejected

- A full 15-state error-state INS (attitude quaternion, three-axis accel / gyro
  biases). Rejected for this increment as far more than the moving-platform twin
  needs; the 4-state unicycle EKF is the canonical, legible nonlinear filter and the
  error-state extension is additive over it.
- Keeping the degrees-space linear filter and only adding the IMU as a second
  position-rate input. Rejected: it would not be an EKF and would not recover
  heading, the point of BL-026.
- A new `imu_status` tool in this increment. Deferred: it would touch the high-blast
  `policy.py` classification; the IMU is observable through the EKF's effect on
  `position_status` for now.

## Revisit triggers

- Bias drift during long GNSS outages becomes material (then error-state accel /
  gyro bias states are added to the EKF).
- A controller needs the raw IMU surface (then `imu_status` lands with its policy
  classification under a follow-on ADR).
- The platform operates over ranges where the single-anchor local-tangent
  approximation degrades (then periodic re-anchoring or an ECEF formulation).
