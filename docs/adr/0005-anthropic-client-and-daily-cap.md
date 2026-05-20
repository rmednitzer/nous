# ADR 0005: Anthropic client with a hard daily cap and prompt-cache discipline

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001

## Context

`inference_cloud` is the seam through which a `nous` deployment talks to
Anthropic. Three operational concerns drove the design:

1. Cost. An unattended simulator can hit a billing surprise quickly.
2. Latency. Repeated calls with the same system prompt should hit the
   prompt cache.
3. Prompt injection. Sensor and operator inputs reach the model;
   trusted and untrusted content must not share a cache slot.

## Decision

`src/nous/anthropic_client.py`:

1. Counts every call against a file-locked daily counter at
   `$NOUS_HOME/.anthropic_daily_count`. The default cap is 100 calls per
   UTC day and is set by `NOUS_ANTHROPIC_DAILY_CAP`. When the cap is
   exhausted, `inference_cloud` raises `CapExhausted` and the caller is
   expected to fall back to `inference_local`.
2. Marks the system prompt and every trusted-context block with
   `cache_control={"type": "ephemeral"}` so repeated calls within the
   cache window pay the input-token discount.
3. Reserves the system slot for trusted content (controller instructions,
   self-model claims, structured engine outputs) and confines untrusted
   content (sensor text, intercepted radio payloads) to the user slot.

The default model is `claude-haiku-4-5-20251001`. Operators who need the
larger model set `NOUS_ANTHROPIC_MODEL_ADVANCED=claude-sonnet-4-6`.

## Consequences

Easier: budget surprises become a configuration knob, not a billing
ticket. Cache discipline is enforced by the client, not by every caller.

Harder: the file-locked counter introduces a small but real I/O cost
per call. The slot discipline must be respected by every callsite.

## Revisit triggers

- Anthropic releases a new model that supersedes the current defaults.
- The cache TTL changes (currently 5 minutes for ephemeral).
- A use case needs multi-tenant per-workspace caps; the file lock is
  single-host today.
