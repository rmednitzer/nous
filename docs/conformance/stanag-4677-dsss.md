# Conformance posture: STANAG 4677 (Dismounted Soldier System data)

**Adapter:** None in v0.1.

**Standard:** STANAG 4677 covers data exchange for dismounted soldier
systems (DSSS). Most relevant for backpack-class units is the
sub-segment covering operator state and unit telemetry.

**v0.1 posture:** Not implemented. `nous` documents its alignment with
DSSS-style operator and unit telemetry but does not emit DSSS-format
messages. The internal `OperatorState` vocabulary (ADR-0006) is
deliberately project-internal; mapping it onto DSSS is an L3 follow-up.

**Tracking:** BL-047 (additional interop adapters).
