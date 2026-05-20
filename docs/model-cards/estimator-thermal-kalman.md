# Model card: Thermal Kalman

**Module:** `src/nous/estimators/thermal.py`

**Backlog:** BL-028

## Inputs

- Junction temperature samples from `ThermalSubsystem.sensor_obs()`.
- Ambient temperature samples.
- Compute load from `ComputeSubsystem.sensor_obs()` (drives the
  process model).

## Outputs

`Estimate` with `point = {junction_c, ambient_c, headroom_c}` and a
3x3 covariance.

## SLA

- Update latency: under 1 ms per call.
- Covariance bound: junction sigma <= 1.5 C in steady state, <= 3.0 C
  during a load transient.

## Known failure modes

- Thermal models assume the heat sink is unobstructed. A pack-borne
  obstruction (clothing, pack contents) inflates the actual junction
  temperature beyond the filter's reported covariance.
- Below -10C ambient the linear thermal-resistance assumption breaks
  down; the filter remains stable but the headroom claim should be
  marked `confidence_low`.
