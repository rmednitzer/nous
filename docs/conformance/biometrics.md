## Conformance posture: operator biometrics

**Subsystem:** `src/nous/subsystems/biometrics.py` (BL-011)

**Estimator:** `src/nous/estimators/biometrics.py` (`BiometricsKalman`)

**MCP tool:** `biometrics_status` (T0)

**Standard alignment:** None. There is no NATO or open-standard
adapter for backpack-class operator biometrics in v0.1. The
subsystem follows the same `Observation` shape as the rest of the
simulator (`nous.types.Observation`) and reuses the SOSA / SSN
mapping documented in `docs/conformance/sosa.md`, but no claim of
medical-grade conformance is made.

**Current posture:** Four channels carried as parametric ground truth
with physiological-range clamps:

- `heart_rate_bpm` clamped to `[20, 240]`
- `core_temp_c` clamped to `[28, 44]`
- `hydration_pct` clamped to `[0, 100]`
- `cognitive_load` (unitless proxy) clamped to `[0, 1]`

Each observation advertises the per-channel sigma sourced from
`profile.sensors.biometrics.*_sigma`; the `BiometricsKalman`
extended for BL-011 tracks all four channels with bounds validation
(a reading outside the physiological range increments
`rejected_updates` without poisoning the central estimate). The
self-model `OperatorState` (NOMINAL / ELEVATED / STRESSED / IMPAIRED
/ INCAPACITATED) is derived from the biometrics estimator each tick
in `src/nous/state/operator_state.py` and surfaced through the
engine's `state.operator_state` (BL-004).

**What is supported:** Parametric ground truth on four channels;
profile-sourced sigmas advertised on every observation;
`set_heart_rate_bpm` / `set_core_temp_c` / `set_hydration_pct` /
`set_cognitive_load` scenario seams; multi-channel Kalman with
physiological-bounds validation; derived `OperatorState` label and
reason on every engine tick.

**What is omitted:** Physiology-grounded model (BL-040, planned for
L2); medical-grade calibration; cross-channel correlations (a
biophysical model would couple core temperature with heart rate
under thermal stress, the simulator does not); per-operator
baselines (one operator, single set of clamps); imaging-based
biometrics (EO / IR thermography, BL-055). Per `LIMITATIONS.md L6`
the biometrics layer exists to exercise the self-model code path,
not to replace medical-grade monitoring.

**Conformance claim:** None. The shape conforms to SOSA / SSN's
observation schema but the simulator is explicit (here and in
`LIMITATIONS.md L6`) that the biometrics values do not represent a
real operator and must not be used for medical decision-making. A
deployment that wants real-operator monitoring needs to replace the
parametric model wholesale and add the calibration evidence that
medical-device conformance demands.

**Cross-references:** `LIMITATIONS.md` L6 (parametric biometrics
scope boundary), SOSA / SSN posture (`docs/conformance/sosa.md`),
operator-state derivation (`src/nous/state/operator_state.py`),
model card for the estimator (`docs/model-cards/`).
