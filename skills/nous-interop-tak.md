---
name: nous-interop-tak
description: Use the CoT/TAK adapter to push a simulated unit position to a TAK server.
---

# CoT / TAK adapter

The CoT adapter encodes a CoT 2.0 `event` element with the required
`time`, `start`, `stale`, and `how` attributes plus a `point` element.
Decoder is XXE-safe (refuses `DOCTYPE` and `ENTITY` declarations).
The conformance posture is documented in
[`docs/conformance/cot-tak.md`](../docs/conformance/cot-tak.md).

## Smoke test

1. Build a payload with `{uid, lat, lon, ts_s}` (the `ts_s` is the
   source estimate timestamp; the encoder refuses to emit if it is
   older than `max_age_s`, default 60 s).
2. Call `interop_encode` (T1, wired per BL-041) with `adapter="cot"`
   and the payload; `interop_decode` round-trips it back.
3. Pipe the bytes to the TAK server's TCP listener.

## What is supported

- Encode and decode (decoder validates root, attributes, and refuses
  XXE constructs).
- `point` with lat / lon / hae and optional `ce` / `le` accuracy.
- `detail.contact.callsign` and `detail.remarks`.

## What is *not* supported

- Mesh delivery, COP overlays, encrypted variants.
- The wider `detail` schema (track, image, shape) and TAK-protocol
  streaming negotiation.

If a scenario needs more, file an item against BL-024.
