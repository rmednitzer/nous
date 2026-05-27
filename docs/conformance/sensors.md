## Conformance posture: environmental sensor pack

**Subsystem:** `src/nous/subsystems/sensors.py` (BL-009)

**Estimator:** `src/nous/estimators/sensors.py` (`EnvironmentalKalman`)

**MCP tool:** `sensors_status` (T0)

**Standard alignment:** OGC / W3C SOSA / SSN (`docs/conformance/sosa.md`).
The subsystem carries ambient temperature, relative humidity, and
barometric pressure as ground truth and emits an `Observation`
(`nous.types.Observation`) that maps to a SOSA `sosa:Observation`:
`source` names the `sosa:Sensor`, `payload` carries the
`sosa:ObservableProperty` values, `noise` carries the per-channel
sigmas that a downstream consumer can map to `sosa:Accuracy` or to
the equivalent SensorThings `unitOfMeasurement.symbol`.

**Current posture:** Three channels per tick: `temp_c` (degrees
Celsius), `humidity_pct` (relative humidity, clamped `[0, 100]`),
`baro_kpa` (barometric pressure, clamped `[10, 200]` kPa). Each
observation advertises the per-channel sigma sourced from
`profile.sensors.environmental.*_sigma`; the
`EnvironmentalKalman` reads those sigmas to size the Kalman gain.
The engine reads `sensors.temp_c` each tick as the thermal
subsystem's ambient input (replacing the v0.1 `_default_ambient_c`
placeholder) so a controller can drive enclosure cooling and the
battery cell temperature through a single `set_temp_c` call.

**What is supported:** Ground-truth ambient state with three
channels; profile-sourced sigmas advertised on every observation;
`set_temp_c` / `set_humidity_pct` / `set_baro_kpa` scenario seams;
multi-channel Kalman with physical-bounds validation (a rejected
reading is counted on `rejected_updates` without poisoning the
central estimate).

**What is omitted:** Per-channel sensor fusion across multiple
physical sensors of the same channel (the simulator carries one
sensor per channel); sensor degradation curves (drift, dropout); EO
or IR imaging surfaces (BL-055); soil / water / radiation channels;
sensor mesh and store-and-forward (BL-056). Real sensor hardware
calibration is out of scope; v0.1 assumes the sigmas in the profile
match the real spec sheet.

**Conformance claim:** None. The shape conforms to SOSA / SSN's
observation schema but the simulator is not a certified SOSA
producer. A downstream consumer that wraps the `Observation` shape
into a SOSA RDF graph or a SensorThings v1.1 `Observation` resource
can claim conformance against the standard independently of the
simulator.

**Cross-references:** SOSA / SSN posture
(`docs/conformance/sosa.md`), SensorThings adapter
(`docs/conformance/ogc-sensorthings.md`), model card for the
estimator (`docs/model-cards/`).
