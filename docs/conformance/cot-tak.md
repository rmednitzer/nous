# Conformance posture: Cursor-on-Target (CoT) and TAK

**Adapter:** `src/nous/interop/cot.py` (BL-024)

**Standard:** CoT is the wire format ATAK / WinTAK / iTAK consume. The
canonical spec lives in the MITRE CoT 2.0 schema.

**v0.1 posture:** The adapter encodes a minimal CoT `event` element
with `type="a-f-G-U-C"` (a friendly ground-unit combatant; chosen as a
neutral default) and a `point` element with lat/lon. Decode is a stub
that records the payload length.

**What is supported:** Encode-only (single-event XML envelope with
lat/lon/hae). The encoded byte stream is suitable for a TAK server's
TCP/UDP listener for smoke tests.

**What is omitted in v0.1:** Decoding inbound CoT, mesh delivery,
nested `detail` elements, COP overlays, encrypted variants. Streaming
adapters and TAK-protocol negotiation land with BL-024 in L2.

**Conformance claim:** None. This is a documented best-effort
compatibility posture, not a certified conformance claim.
