# Conformance posture: MOSA

**Standard:** Modular Open Systems Approach (MOSA), the DoD-driven
practice of decomposing systems into modular, openly-interfaced
components.

**v0.1 posture:** `nous` is architected for MOSA-style modularity:
subsystems and estimators are pluggable via Protocols, the policy and
runner are independent of any tool, and interop adapters share a
single Protocol. Each adapter is replaceable without touching the
engine.

**What is supported:** The architecture *patterns* MOSA encourages.

**What is omitted in v0.1:** A MOSA-style key-interface profile (KIP)
or conformance certification. The simulator does not claim MOSA
conformance, only architectural alignment.

**Tracking:** No backlog item; alignment is a property of the
architecture and is preserved by ADR-0007 (additive-surface rule) and
ADR-0011 (single adapter Protocol).
