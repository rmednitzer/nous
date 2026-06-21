# Model card: Position (nonlinear EKF, GNSS/INS fusion)

**Module:** `src/nous/estimators/position_ekf.py` (`PositionEkf`, the engine's
active position estimator since BL-026 / ADR 0073, extended to an error-state filter
with online IMU bias estimation in ADR 0076). The degrees-space linear filter
`src/nous/estimators/position.py` (`PositionKalman`) is retained for reference and
its own unit tests but is no longer wired into the engine.

**Backlog:** BL-026

## Inputs

- GNSS fix observations from `PositionSubsystem.sensor_obs()` (lat, lon, alt_m, with
  per-axis sigma), folded as the measurement update.
- IMU observations from `ImuSubsystem.sensor_obs()` (`accel_mps2` longitudinal
  specific force, `yaw_rate_rps`), consumed as the control that drives the
  prediction (`obs.source == "imu"`).

## Outputs

`Estimate` with `point = {lat, lon, alt_m, speed_mps, heading_deg, v_e_mps,
v_n_mps, accel_bias_mps2, gyro_bias_rps}` and `covariance` keyed by `{lat, lon,
alt_m, e_m, n_m, speed_mps, heading_rad, accel_bias_mps2, gyro_bias_rps}` (lat / lon
variances are the metre variances mapped back to degrees). The legacy
degrees-per-second velocity keys (`v_lat` / `v_lon` / `v_alt_m`) had no consumer and
are dropped (ADR 0073). The bias keys are additive over the ADR 0073 surface
(ADR 0076).

The state `[e, n, v, psi, b_a, b_omega]` lives in a local east-north-up tangent frame
anchored on the first fix: east / north metres, ground speed (m/s), heading (rad,
clockwise from north), and the accelerometer and yaw-rate gyro biases. The process is
the unicycle model `de = v sin(psi) dt`, `dn = v cos(psi) dt`, nonlinear in psi, so
`predict` propagates the covariance through the analytic Jacobian: a genuine EKF, not
the degrees-space linear filter it supersedes. `predict` subtracts the estimated bias
before integrating the IMU, so a constant bias accrues a position error that GNSS
observes. GNSS observes only position; speed, heading, and both biases are recovered
through the cross-covariance the motion builds up. Altitude is a decoupled scalar
channel.

## SLA

- Update latency: under 5 ms per call on the reference profile (a 6x6 EKF plus a
  2x2 matrix inverse).
- Covariance bound at the 95th percentile under nominal fix quality: horizontal
  sigma <= 5 m, vertical sigma <= 8 m, with a 1 m horizontal variance floor so a
  converged filter stays honest about GNSS noise.

## Known failure modes

- GNSS multipath in urban canyons inflates the actual horizontal error beyond the
  filter's reported covariance; the chi-square gate rejects an outlier fix, but a
  sustained biased fix is adopted through the re-anchor reset.
- IMU-only periods (lost fix): the EKF coasts on the de-biased inertial solution,
  holding the inferred velocity and heading once the bias states have converged
  (ADR 0076), so a constant bias no longer walks the coast. The covariance still
  grows while dead-reckoning, and a bias that drifts faster than the random-walk
  process noise tracks will still pull the solution; past tens of seconds without a
  fix the bound is no longer defensible.
- Unexcited bias states (stationary, or no fix yet): the biases are observable only
  through motion and a position fix, so a filter that has not moved leaves them near
  zero with a wide variance rather than committing to a value. This is the honest
  posture, but it means the bias estimate is only meaningful after the platform has
  manoeuvred under GNSS.
- Over ranges where the single-anchor local-tangent approximation degrades (hundreds
  of km from the anchor) the ENU mapping loses accuracy; periodic re-anchoring or an
  ECEF formulation is the revisit trigger (ADR 0073).
