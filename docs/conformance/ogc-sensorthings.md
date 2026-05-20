# Conformance posture: OGC SensorThings

**Adapter:** `src/nous/interop/sensorthings.py` (BL-025)

**Standard:** OGC SensorThings v1.1, the JSON API for IoT
observations. Spec: <https://www.ogc.org/standard/sensorthings/>.

**v0.1 posture:** Encode emits a single-observation JSON envelope with
`@iot.id`, `phenomenonTime`, `result`, and `Datastream.name`. Decode
parses inbound JSON envelopes back to a dictionary.

**What is supported:** Observation envelopes, the SOSA/SSN-aligned
field names. The encoded JSON is suitable for `POST
/Observations` against a compliant SensorThings server.

**What is omitted in v0.1:** Streaming via MQTT or websockets (use the
MQTT adapter for the smoke test), batch insertion, FeatureOfInterest
linking, complex result types (Categorical, Truth, Count). These land
with BL-025 in L2.

**Conformance claim:** None. v0.1 documents intent and shape; no
SensorThings test suite has been run.
