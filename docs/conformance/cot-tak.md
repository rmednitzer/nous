# Conformance posture: Cursor-on-Target (CoT) and TAK

**Adapter:** `src/nous/interop/cot.py` (BL-024)

**Standard:** CoT is the wire format ATAK / WinTAK / iTAK consume. The
canonical spec lives in the MITRE CoT 2.0 schema.

**Current posture:** The adapter encodes a CoT 2.0 `event` element
with `type="a-f-G-U-C"` by default (a friendly ground-unit combatant;
override via `data["type"]`), explicit `time`, `start`, and `stale`
attributes, `how="m-g"` (machine, GPS), and a `point` element with
lat / lon / hae / ce / le. Attribute values are escaped with
`xml.sax.saxutils.quoteattr`. The encoder refuses to emit when the
source estimate is older than `max_age_s` (default 60 s, configurable
per ADR 0011 freshness rule SC-4). Decode is a narrow XML reader that
explicitly refuses `DOCTYPE` and `ENTITY` declarations (XXE-safe).

**What is supported:** Single-event encode and decode, lat / lon / hae
plus optional `ce` / `le` accuracy, `detail.contact.callsign`,
`detail.remarks`. The encoded byte stream is suitable for a TAK
server's TCP / UDP listener.

**What is omitted:** Mesh delivery, COP overlays, encrypted variants,
the wider `detail` schema (track, image, shape). The TAK-protocol
negotiation lands with the streaming adapter follow-up.

**Conformance claim:** None. This is a documented best-effort
compatibility posture, not a certified conformance claim. The 2026-05-23
audit confirmed the required-attribute completeness (closes the
baseline H3 finding).
