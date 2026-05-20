# Model card: Biometrics Kalman

**Module:** `src/nous/estimators/biometrics.py`

**Backlog:** BL-029

## Inputs

- Heart rate, core temperature, hydration, and cognitive load proxy
  from `BiometricsSubsystem.sensor_obs()`.

## Outputs

`Estimate` with `point = {heart_rate_bpm, core_temp_c, cognitive_load}`
and a 3x3 covariance. The self-model layer maps the estimate onto the
`OperatorState` vocabulary.

## SLA

- Update latency: under 1 ms per call.
- Covariance bound: heart rate sigma <= 4 bpm, core temperature sigma
  <= 0.1 C in steady state.

## Known failure modes

- The biometrics subsystem in v0.1 is *parametric*, not
  physiology-grounded (see `LIMITATIONS.md` L6). The Kalman filter is
  well-bounded against the parametric model and *not* against a real
  human signal.
- High-intensity transients (sprinting, sudden cold shock) violate the
  linear-Gaussian assumption; the filter remains numerically stable
  but the covariance bound is no longer defensible.
