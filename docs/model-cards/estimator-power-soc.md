# Model card: Power SoC

**Module:** `src/nous/estimators/power.py`

**Backlog:** BL-027

## Inputs

- Battery voltage and current from `PowerSubsystem.sensor_obs()`.
- Cell temperature from `ThermalSubsystem.sensor_obs()` (for the
  Peukert correction).

## Outputs

`Estimate` with `point = {soc_pct, voltage_v, current_a, load_w}` and a
three-entry diagonal covariance over `soc_pct`, `voltage_v`, and `load_w`.
`current_a` is the last observed value passed through verbatim: it is not
filtered and has no covariance entry. `load_w` (ADR 0083) is the total
electrical load the battery sees, a well-known engine input, so its channel
carries a small observation noise and converges tightly; the self-model reads
this belief for endurance rather than ground truth.

## SLA

- Update latency: under 1 ms per call.
- Covariance bound: SoC sigma <= 2 percentage points at >20% SoC,
  <= 5 percentage points below 20%.

## Known failure modes

- Coulomb counting alone diverges over multi-day runs; the voltage
  update bounds the drift but introduces noise. Calibrate against a
  full charge/discharge cycle on the actual cell.
- Cold-cell behaviour deviates from the Peukert correction below 0C;
  the model card explicitly does not bound the error there.
