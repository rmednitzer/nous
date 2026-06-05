# Model card: Position EKF

**Module:** `src/nous/estimators/position.py`

**Backlog:** BL-026

## Inputs

- GNSS fix observations from `PositionSubsystem.sensor_obs()` (lat,
  lon, alt_m, with per-axis sigma).
- IMU integrals (accel + gyro) once the L2 IMU model lands.

## Outputs

`Estimate` with `point = {lat, lon, alt_m, v_lat, v_lon, v_alt_m}` (the
three velocity channels are degrees-per-second per axis) and a six-entry
diagonal covariance keyed by the same names. The filter stays diagonal (no
cross-covariance); a full 6x6 EKF with cross terms is deferred to BL-061.

## SLA

- Update latency: under 5 ms per call on the reference profile.
- Covariance bound at the 95th percentile under nominal fix quality:
  horizontal sigma <= 5 m, vertical sigma <= 8 m.

## Known failure modes

- GNSS multipath in urban canyons inflates the actual horizontal error
  beyond the filter's reported covariance; treat indoor or near-wall
  fixes as `confidence_low`.
- IMU-only periods (lost fix) accumulate error linearly with time;
  past 30 s of dead reckoning the covariance bound is no longer
  defensible.
