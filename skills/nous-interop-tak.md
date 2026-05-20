---
name: nous-interop-tak
description: Use the CoT/TAK adapter to push a simulated unit position to a TAK server.
---

# CoT / TAK adapter

The CoT adapter encodes a minimal `event` element. The conformance
posture is documented in `docs/conformance/cot-tak.md`.

## Smoke test

1. Build a payload with `{uid, lat, lon}`.
2. Call `interop_encode` (L2) with `adapter="cot"` and the payload.
3. Pipe the bytes to the TAK server's TCP listener.

## What is *not* supported in v0.1

- Decode (inbound CoT messages).
- Nested `detail` elements (operator state, COP overlays).
- Encrypted variants.

If a scenario needs more, file an item against BL-024.
