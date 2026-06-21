# Model card: EO/IR detection-range Kalman

**Module:** `src/nous/estimators/eoir.py`

**Backlog:** BL-055

## Inputs

- Per-band effective detection ranges (`eo_range_m`, `ir_range_m`) from
  `EoirSubsystem.sensor_obs()`, with a measurement sigma that the subsystem
  widens as the focal-plane calibration drifts (`base_sigma / cal_factor`), so a
  poorly calibrated payload's reading is folded more gently. A reading is rejected
  (and counted in `rejected_updates`) if it is non-finite or outside its physical
  bound (each band in [0, 60000] m), so a wild sample cannot poison the central
  estimate. `predict` inflates each channel's variance with a small per-second
  process sigma (50 m).

## Outputs

`Estimate` with `point = {eo_range_m, ir_range_m}` and a matching two-entry
diagonal covariance (one variance per band, no cross-covariance).

## SLA

- Update latency: under 1 ms per call.
- Covariance bound: each band's sigma converges toward its (calibration-scaled)
  observation sigma in steady state; the small process variance keeps the
  estimate responsive when an obscurant or a thermal crossover moves the truth.

## Known failure modes

- Bounds rejection guards against an out-of-range reading, but a reading that is
  in range and merely wrong is accepted; the filter has no stuck-channel
  detection.
- The two bands degrade under different physics (illumination versus thermal
  contrast, different atmospheric coupling) but are filtered independently; the
  filter does not exploit any relationship between them.
- The filter tracks the detection-range envelope the subsystem reports; it does
  not itself model occlusion, target signature, or scene content. Its covariance
  is honest about measurement and calibration uncertainty, not about whether the
  envelope model is the right one for a given scene.
