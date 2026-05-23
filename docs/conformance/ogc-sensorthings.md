# Conformance posture: OGC SensorThings

**Adapter:** `src/nous/interop/sensorthings.py` (BL-025)

**Standard:** OGC SensorThings v1.1, the JSON API for IoT
observations. Spec: <https://www.ogc.org/standard/sensorthings/>.

**Current posture:** Encode emits a single-observation JSON envelope
with `@iot.id`, `result`, `phenomenonTime` and `resultTime` (both
normalised to UTC ISO-8601 with the `Z` suffix per OGC SensorThings
v1.1 §6.5), and `Datastream.name`. Encoder refuses to emit when the
source estimate is older than `max_age_s` (default 60 s); both encode
and decode enforce `max_payload_len` (default 64 KiB) to bound the
attack surface against oversized payloads. Decode parses inbound JSON
envelopes back to a dictionary, returning `{"error": ...}` on parse
failure rather than raising.

**What is supported:** Observation envelopes, the SOSA / SSN-aligned
field names. The encoded JSON is suitable for `POST /Observations`
against a compliant SensorThings server.

**What is omitted:** Streaming via MQTT or websockets (use the MQTT
adapter for the smoke test), batch insertion, FeatureOfInterest
linking, complex result types (Categorical, Truth, Count).

**Conformance claim:** None. The 2026-05-23 audit confirmed UTC
normalisation of `phenomenonTime` (closes the baseline H4 finding).
