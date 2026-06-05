# Model card: Thermal Kalman

**Module:** `src/nous/estimators/thermal.py`

**Backlog:** BL-028

## Inputs

- Junction and enclosure temperature samples from
  `ThermalSubsystem.sensor_obs()`. The process model adds a fixed
  per-second process variance on `predict`; it is not driven by compute
  load.

## Outputs

`Estimate` with `point = {junction_c, enclosure_c}` and a matching
two-entry diagonal covariance (one variance per channel, no
cross-covariance). `ambient_c` and `headroom_c` are subsystem-level reads,
not filter state. A full multi-state thermal filter is deferred to BL-028.

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
