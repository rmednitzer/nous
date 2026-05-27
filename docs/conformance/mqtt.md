## Conformance posture: MQTT

**Adapter:** `src/nous/interop/mqtt.py` (BL-036)

**Standard:** MQTT v3.1.1 (OASIS) and MQTT v5.0 wire-level
compatibility for the publish-payload shape. The adapter does not
implement the protocol itself; it produces and consumes the JSON
envelope a publisher or subscriber would carry as the application
payload of a `PUBLISH` packet.

**Current posture:** Encode stamps an ISO-8601 `ts` (UTC, `Z`-suffixed)
on every JSON envelope sourced from a fresh estimate; the freshness
guard refuses to encode when the source is older than `max_age_s`
(default 30 s) per SC-4. Encode and decode enforce `max_payload_len`
(default 64 KiB) so a broker amplification cannot inflate the audit
record or the MCP response body. Decode returns `{"error": ...}` on
parse failure rather than raising, so a malformed broker message
cannot crash the runner.

**What is supported:** JSON-over-MQTT envelope encode and decode. The
envelope mirrors the source mapping the controller passes; `ts`
defaults to the source estimate's `ts_s` rendered as UTC ISO-8601.
Wire-format compatible with any consumer expecting JSON application
payloads on an MQTT topic.

**What is omitted:** Live broker connect / publish / subscribe via
`paho.mqtt.client` (the dependency is on the wheel but the v0.1
adapter is encode-only, see ADR 0011). MQTT v5 user properties,
content-type, response topics. QoS configuration, retained messages,
last-will-and-testament, session persistence. TLS, mTLS, OAuth
client-credentials over MQTT, broker-side topic ACL enforcement.

**Conformance claim:** None. The adapter is a JSON-envelope shaper;
it is not a certified MQTT v3.1.1 or v5 client. A downstream
publisher implementing this envelope can claim conformance against
its broker independently of the simulator.

**Defaults that should be revisited by a deployment review:** The
encode-only posture means a controller that needs telemetry on a
real broker pairs the adapter's output with a separately-managed
`paho.mqtt.client.Client` (or any wire-compatible client). QoS
choice, retained behaviour, last-will, and topic ACL are the
deployment's responsibility; the simulator does not assume any of
them. The freshness threshold (`max_age_s`) and the payload bound
(`max_payload_len`) are conservative defaults sized for a
single-operator telemetry feed; a high-throughput sensor stream
would raise the latter and a long-cadence health beacon would raise
the former.
