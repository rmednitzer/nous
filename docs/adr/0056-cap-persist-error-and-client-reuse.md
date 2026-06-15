# ADR 0056: Distinguish a cap-persistence failure from exhaustion, and reuse the client

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0005, ADR 0034, ADR 0035, ADR 0049, ADR 0050

## Context

Two findings from the 2026-06-14b audit touch the cloud inference path. MED-1:
`inference_cloud` constructed a fresh `AnthropicClient` inside its per-call
`_work` body, so every call built a new `AsyncAnthropic` (a new httpx connection
pool) and discarded the previous client's `last_cache_read_input_tokens`, the
one signal that makes the prompt-cache discipline observable (ADR 0035). The
`@lru_cache build_client()` singleton that should have prevented this exists but
is dead code, and it reads the global `get_settings()` rather than the running
app's settings, so wiring it would have ignored an injected `Settings` and
risked cross-test cache pollution.

LOW-3: `CallCap.increment` raised `CapExhausted` when `os.fsync` failed on the
counter file. The fsync runs after the count is written and flushed, so the
failure is a durability problem, not an exhausted budget, yet the fallback
ladder rendered it to the operator as `reason: "cap exhausted: ... could not be
fsynced"`. A controller reading that reason during a transient disk fault would
conclude the daily budget was spent when it was not.

## Decision

For MED-1, the app owns one client. `Nous` builds one `AnthropicClient` from
`self.settings` eagerly in its constructor and exposes it as `anthropic_client`;
`inference_cloud` reads `app.anthropic_client` instead of constructing its own.
The eager single assignment makes the one-per-process guarantee hold
unconditionally rather than via a `cached_property`, whose first-access compute
is not thread-safe on Python 3.12+ (the SDK construction needs no running event
loop, so building at construction is safe). The client is reused across calls so
the httpx pool and the cache metric persist, and it honours an injected
`Settings`. The dead `build_client()` global is left untouched but is superseded
for the tool path; the cache-control markers in `AnthropicClient.call` are
unchanged, so the prompt-cache discipline is preserved (reuse only strengthens
it).

For LOW-3, the fsync-durability failure raises a new `CapPersistError`,
independent of `CapExhausted` (both subclass `RuntimeError`). The fallback ladder
catches it with an honest reason (`"cap not persisted: ..."`) and still degrades
to the local mock, so the fail-closed posture from ADR 0049 is unchanged while
the surfaced reason stops misreporting a disk fault as exhaustion. Because the
write and flush precede the fsync, a fsync failure may have already advanced the
on-disk count; failing closed (treating the slot as spent) is the conservative
choice and is consistent with ADR 0050, where the on-disk tail is authoritative
and the fsync is only the durability confirmation.

## Consequences

A controller can now tell a transient durability fault from a genuinely
exhausted cap on the fallback `reason`, and the cloud path no longer churns a
connection pool per call. The cache-read metric survives across calls, so the
ADR 0035 discipline is observable as intended. The only behaviour a caller sees
change is the fallback reason on the rare fsync-failure path, and a single client
identity for the process.

The cost is one more exception type on the cap surface and one client built at
`Nous` construction. The audit's literal suggestion (wire `build_client()`) was
rejected
because it would bind the tool to the global settings rather than the app's.
Closes BL-092. Covered by additions to `tests/unit/test_anthropic_client.py`,
`tests/unit/test_inference_fallback.py`, and the `TestMed1` / `TestLow3`
regression classes (ADR 0023).

## Revisit triggers

Remove or repurpose `build_client()` if a second caller needs a process-global
client, or if the dead symbol is judged a maintenance hazard. Revisit the
slot-spent-on-fsync-failure choice if a counter layout that fsyncs before the
visible write becomes worthwhile (it would let a fsync failure leave the count
unadvanced, at the cost of a more complex two-phase write).
