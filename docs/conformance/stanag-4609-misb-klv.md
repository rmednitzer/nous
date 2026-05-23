# Conformance posture: MISB KLV (Key-Length-Value)

**Adapter:** `src/nous/interop/misb_klv.py` (BL-032)

**Standard:** MISB ST 0601 UAS Metadata in the KLV (SMPTE 336M)
encoding, layered on STANAG 4609 video. Spec:
<https://gwg.nga.mil/misb/>.

**Current posture:** Encode emits a UAS LDS universal-key prelude
followed by a BER-length-prefixed body of TLV tuples. Local-set keys
are validated to the `[1, 255]` range; value lengths use BER
short-form for values under 128 bytes and BER long-form above; the
encoder refuses to truncate either the key or the length and raises
`ValueError` on overflow. Key 2 (`Unix Time Stamp`) is stamped on
every encode and the encoder refuses to emit when the source estimate
is older than `max_age_s` (default 30 s). Decode validates the
universal key, parses the BER length, walks the TLV stream, and
returns `{"error": ...}` on a truncated or malformed payload.

**What is supported:** ST 0601 local-set encode and decode with proper
BER length handling. Suitable for smoke testing a downstream MISB
parser; not certified for production.

**What is omitted:** Full ST 0601 tag dictionary (the encoder accepts
any integer key but the decoder returns raw value bytes), universal-set
checksum (key 1), STANAG 4609 video container, embedding in a transport
stream.

**Conformance claim:** None. A real MISB integration goes through a
certified parser; this adapter is for simulator outputs only. The
2026-05-23 audit confirmed BER-OID length handling (closes the
baseline C4 finding).
