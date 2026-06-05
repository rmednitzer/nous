# Modelling assumptions and simplifications

> **Fidelity disclaimer.** `nous` is a simulation-based digital twin of an
> edge-AI inference appliance. It does not drive real hardware and is not
> suitable for safety-of-flight, mission-licensing, or certification
> decisions. The simplifications documented below introduce modelling
> errors that the codebase does not bound. Any use of `nous` in a
> regulatory, procurement, or operational decision must be assessed
> independently against a higher-fidelity model and against the real
> device's behaviour.

This document is the per-subsystem counterpart to `LIMITATIONS.md`.
`LIMITATIONS.md` lists the *scope boundaries* of the project (what
`nous` is not yet, and what it does not aim to be). This document
records the *modelling shortcuts* inside the components that do exist,
each cross-referenced to its source file so a reviewer can trace an
assumption back to the line of code that embodies it.

When a subsystem is rewritten and a simplification disappears, delete
the bullet. When a new subsystem lands, add a section in the same
shape. Conformance posture per external standard lives in
`docs/conformance/`; modelling assumptions internal to a subsystem
live here.

## Power (Li-ion battery)

`src/nous/subsystems/power.py`. The battery is modelled as a single
Li-ion pack with a Peukert capacity correction, a thermal derate, and
an internal-resistance voltage drop. Charge input is integrated from
the APU.

- Single chemistry. Li-ion only; LiFePO4 and solid-state chemistries
  are tracked under BL-042. State-of-charge is treated as a scalar in
  ``[0, 100]``; there is no cell-level model and no pack imbalance.
- Peukert exponent is profile-supplied and treated as constant across
  temperature. Real Li-ion capacity loss under high current at low
  temperature is steeper than the Peukert curve predicts.
- Thermal derate is a linear scaling between ``thermal_derate_c`` and
  the cell temperature reported by the thermal subsystem. There is no
  hysteresis and no cycle-aging model.
- Internal resistance is a single scalar per profile. SOC- and
  temperature-dependent resistance are not modelled.

## APU (auxiliary power)

`src/nous/subsystems/apu.py`. The APU bank is auxiliary by design
(ADR-0015). It charges the battery but never delivers power directly
to the load.

- Each source (solar, fuel cell, kinetic) is a scalar Wattage with a
  profile-supplied availability schedule. There is no irradiance
  model, no fuel-cell stack thermal model, and no kinetic-harvester
  drivetrain model.
- The bus regulator clamps total APU power to ``charge_limit_w``.
  Regulator efficiency is treated as unity.

## Thermal (lumped two-mass)

`src/nous/subsystems/thermal.py`. Junction and enclosure temperatures
evolve under a two-mass lumped-capacitance model driven by the compute
draw and ambient temperature.

- Two lumps only. There is no spatial gradient inside either mass.
  The model is valid only when the real device's hot-spot delta to
  the bulk junction temperature stays within a few degrees; under
  sustained workload that assumption breaks.
- Heat transfer coefficients are profile-supplied scalars. There is
  no airflow model, no orientation dependence, and no thermal-paste
  degradation.
- Throttling is a single threshold on junction temperature. Real
  silicon throttle profiles are usually multi-stage (P-state, T-state,
  emergency cutoff).

## Compute (load + draw)

`src/nous/subsystems/compute.py`. Compute load and draw are scalars in
``[0, 100]%`` and Watts respectively. Throttling on a thermal flag
reduces both proportionally.

- No workload-class model. A 50 percent load is treated as drawing
  half the rated power regardless of whether the work is dense matrix
  multiply, inference decode, or idle wait. Real inference accelerators
  exhibit very different power profiles per workload.
- DVFS is implicit: ``draw_w`` follows ``load_pct`` linearly. There is
  no explicit P-state model.

## Inference (local, mocked)

`src/nous/subsystems/inference.py`. The local-inference path simulates
tokens-per-second and energy-per-token from profile constants.
`inference_local` does not actually run a model.

- Throughput and energy are profile constants; there is no batch-size
  effect, no prefill / decode split, and no KV-cache memory pressure.
  Real inference latency and energy are strong functions of these.
- No model-quality regression. A "throttled" inference call returns
  fewer tokens at the same per-token energy, not a degraded answer.

## Storage (used + wear)

`src/nous/subsystems/storage.py`. Disk usage and wear are scalars; the
worn-out and at-capacity flags fire on profile thresholds.

- Wear is modelled as a linear function of writes per second. Real
  flash wear is non-linear, has per-block hot-spots, and depends on
  whether the controller can amplify writes through GC.
- No filesystem model. Storage cannot become "fragmented" or "slow"
  short of crossing the wear threshold.

## Comms (per-link envelopes)

`src/nous/subsystems/comms.py`. Each link from `profile["comms"]["links"]`
carries an RSSI / loss / throughput / age tuple. Links time out after
`max_age_s`.

- Link envelopes are independent. There is no contention between
  links sharing a band, no antenna pattern, and no near-field
  interference. SATCOM startup latency, jitter, and outage windows
  are tracked under BL-057.
- The link-state derivation collapses the population to one of three
  enum values (`CONNECTED`, `DEGRADED`, `LOST`). A controller cannot
  read per-link confidence without ``comms_status``.

## Position (GNSS + IMU dead-reckoning)

`src/nous/subsystems/position.py`. Ground truth advances by
dead-reckoning each tick; GNSS sensor observations carry profile
sigmas. Loss of fix widens the position Kalman variance through
predict-only.

- Dead-reckoning treats heading as exact. Real IMU drift is correlated
  across axes and grows roughly as the cube root of time; the full
  Kalman filter is tracked under BL-026.
- Altitude is barometric in profile shape but here is treated as a
  free state. There is no terrain model.
- No multi-path. GNSS sigmas are constant per profile and do not
  reflect urban-canyon or foliage-attenuation effects.

## Sensors (environmental)

`src/nous/subsystems/sensors.py`. Ambient temperature, humidity, and
barometric pressure are scenario-driven scalars. There is no
correlation between channels.

- The atmosphere is treated as one cell. There is no microclimate, no
  latency between an environmental change and the sensor reading
  (other than the tick cadence), and no humidity-temperature
  cross-coupling.

## Biometrics (operator state)

`src/nous/subsystems/biometrics.py`. Heart rate, core temperature,
hydration, and cognitive load are scalars driven by scenario events
and clamped to physiological bounds.

- No operator-specific calibration. The bounds (HR in 20..240 bpm,
  core temperature in 28..44 C) apply to all operators uniformly.
- No coupling between channels. A real operator's cognitive load
  rises with thermoregulatory stress; here the four channels evolve
  independently.
- Stub estimator. ``BiometricsKalman`` is a per-channel 1-D filter
  with rejected-update tracking (BL-029). The full physiology-grounded
  model is L2 work.

## Inferential layers (estimators and self-model)

`src/nous/estimators/`, `src/nous/self_model/`. The estimator stack
returns calibrated beliefs over each subsystem state; the self-model
aggregates those beliefs into capability claims.

- Every estimator is 1-D or per-channel diagonal. There is no
  cross-channel covariance, so a correlated drift in two related
  measurements is not captured.
- ``self_model/assess.py`` and ``self_model/viability.py`` are wired
  (BL-018): they aggregate estimator posteriors into capability claims with
  calibrated ``p5``/``p50``/``p95`` quantiles (Monte Carlo by default,
  BL-035) and a confidence. The remaining gap is a *learned* self-model;
  the current claims are model-derived, so treat a low ``confidence`` or a
  collapsed band as low information rather than a precise answer.

## Scenarios

`src/nous/scenarios/loader.py`. The loader is currently a typed-stub
(BL-014). Scenario YAML files in `scenarios/` describe injected
events, but the dispatcher that replays them through the engine is
the L2 deliverable. Today the scenario seam exists; the replay does
not.

## Adapters (interop)

`src/nous/interop/`. Each adapter encodes the simulator's view into a
target standard format. Conformance claims per adapter live in
`docs/conformance/`; this section records only the modelling
assumptions about the source data.

- Encoders take the simulator's *belief* (point estimate plus
  covariance) and stamp the source timestamp into the wire format.
  The covariance is dropped unless the target standard has a place
  for it (`ce` / `le` on CoT, SensorThings observation
  ``resultQuality``).
- Adapters refuse to emit when the source estimate is older than
  ``max_age_s``. The default is per-adapter (`docs/conformance/*`),
  not a single global; a controller running multiple adapters sees
  the strictest one fire first.
