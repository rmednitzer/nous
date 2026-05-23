# Model card: Biometrics Kalman

**Module:** `src/nous/estimators/biometrics.py`

**Backlog:** BL-029

## Inputs

- Heart rate, core temperature, hydration, and cognitive load proxy
  from `BiometricsSubsystem.sensor_obs()`. Profile sigmas under
  `sensors.biometrics` size the Kalman gain on each channel.

## Outputs

`Estimate` with `point = {heart_rate_bpm, core_temp_c, hydration_pct,
cognitive_load}` and a 4x4 (diagonal) covariance. Invalid readings
are rejected and tallied on `rejected_updates` without poisoning the
central estimate. The self-model layer maps the estimate onto the
`OperatorState` vocabulary.

## SLA

- Update latency: under 1 ms per call.
- Covariance bound: heart rate sigma <= 4 bpm, core temperature sigma
  <= 0.1 C, hydration sigma <= 1 percentage point, cognitive-load
  sigma <= 0.05 in steady state.

## Known failure modes

- The biometrics subsystem in v0.1 is *parametric*, not
  physiology-grounded (see `LIMITATIONS.md` L6). The Kalman filter is
  well-bounded against the parametric model and *not* against a real
  human signal.
- High-intensity transients (sprinting, sudden cold shock) violate the
  linear-Gaussian assumption; the filter remains numerically stable
  but the covariance bound is no longer defensible.
