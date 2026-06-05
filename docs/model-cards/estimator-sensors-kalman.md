# Model card: Environmental sensor Kalman

**Module:** `src/nous/estimators/sensors.py`

**Backlog:** BL-009, BL-050

## Inputs

- Ambient temperature, relative humidity, and barometric pressure from
  `SensorsSubsystem.sensor_obs()`, with the profile-advertised per-channel
  sigmas. A reading is rejected (and counted in `rejected_updates`) if it is
  non-finite or outside its physical bound (`temp_c` in [-90, 90],
  `humidity_pct` in [0, 100], `baro_kpa` in [10, 200]), so a wild sample
  cannot poison the central estimate. `predict` inflates each channel's
  variance with a small per-second process sigma (`0.05 C`, `0.2 %`,
  `0.05 kPa`).

This estimator is the authoritative ambient source: the engine reads
`sensors.temp_c` each tick as the thermal subsystem's ambient input.

## Outputs

`Estimate` with `point = {temp_c, humidity_pct, baro_kpa}` and a matching
three-entry diagonal covariance (one variance per channel, no
cross-covariance).

## SLA

- Update latency: under 1 ms per call.
- Covariance bound: each channel's sigma converges toward its advertised
  observation sigma in steady state; the small process variance keeps the
  estimate from going stale between updates.

## Known failure modes

- Bounds rejection guards against an out-of-range reading, but a reading that
  is in range and merely wrong (a stuck sensor pinned at a plausible value)
  is accepted; the filter has no stuck-channel detection.
- If the observation advertises no sigma for a channel (sigma 0), the update
  hard-sets the estimate to the raw reading rather than smoothing it, so an
  unadvertised channel is passed through unfiltered. The shipped subsystem
  always advertises a sigma; a custom profile that omits one loses the
  filtering on that channel.
- The three channels are physically related (temperature shifts relative
  humidity, altitude couples temperature and pressure) but are filtered
  independently; the filter does not exploit those relationships.
