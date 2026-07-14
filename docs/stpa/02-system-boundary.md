# 02 -- System boundary

**Inside the system**

- The simulator process (`nous serve` / `nous tick` / `nous scenario`).
- The MCP tool surface that a controller drives.
- The audit log and the SQLite state database.
- The OAuth issuer for HTTP transport.
- The interop adapters (CoT/TAK, SensorThings, MISB KLV, NMEA 0183,
  STANAG 4774/4778, MQTT).

**Outside the system**

- The Anthropic API (the `inference_cloud` call site reaches outside the
  boundary).
- The TAK server, MQTT broker, or other downstream consumer of an
  adapter's output.
- The operator's body and environment. The biometric subsystem
  produces parametric outputs about a *simulated* operator; the
  hazards of harming a real operator are out of scope.
- The deployment VM kernel and Linux distribution. Faults there are
  treated as a deployment environment concern, not a `nous` concern.

The boundary is what makes the simulator simulable: everything inside
is observable, controllable, and replayable.
