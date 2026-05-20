# Conformance posture: MISB KLV (Key-Length-Value)

**Adapter:** `src/nous/interop/misb_klv.py` (BL-032)

**Standard:** MISB ST 0601 UAS Metadata in the KLV (SMPTE 336M)
encoding, layered on STANAG 4609 video. Spec:
<https://gwg.nga.mil/misb/>.

**v0.1 posture:** Encode emits a flat byte stream of single-byte
key/length/value tuples. Decode is a stub that records the payload
length. Local-set tags, BER-OID encoding, and the universal-set
prelude land with BL-032.

**What is supported:** A minimal byte-level TLV encoder useful for
smoke testing a downstream MISB parser. Not suitable for production.

**What is omitted in v0.1:** Full ST 0601 tag dictionary, BER-OID
length encoding, universal-set checksum, STANAG 4609 video container,
embedding in a transport stream.

**Conformance claim:** None. A real MISB integration goes through a
certified parser; this adapter is for simulator outputs only.
