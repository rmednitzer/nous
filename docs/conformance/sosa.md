# Conformance posture: SOSA / SSN

**Standard:** W3C Semantic Sensor Network (SSN) ontology and its core
SOSA (Sensor, Observation, Sample, and Actuator) module.

**v0.1 posture:** `nous` aligns its `Observation` and `Estimate`
types (`src/nous/types.py`) with the SOSA concepts of *observation*
(`Observation`), *result* (`result`), and *feature of interest* (the
implicit subsystem). The alignment is *conceptual*; no JSON-LD or
RDF emission ships in v0.1.

**Tracking:** A SOSA JSON-LD adapter is a candidate follow-up under
BL-047 if downstream consumers need it. The SensorThings adapter
already carries the SOSA-aligned field names.
