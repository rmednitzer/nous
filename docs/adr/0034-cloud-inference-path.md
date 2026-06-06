# ADR 0034: Register the cloud inference path

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0005 (Anthropic client and daily cap), ADR 0021 (inference tools), ADR 0033 (complete tool surface)

## Context

BL-013 built the local inference path and deferred the cloud path "to a
follow-up ADR." In the time since, the three pieces the cloud path needs were
built and tested on their own: the file-locked daily cap and the capped
`AnthropicClient.call` (ADR 0005), the structured `CapExhausted` payload
(BL-021, `anthropic_status.py`), and the `InferenceFallback` ladder
(`inference_fallback.py`) that prefers the cloud and degrades to the local
mock. The one missing piece was a controller-facing tool: `inference_cloud`
was classified T2 in `policy.py` but never registered, so the capability was
analysed and dormant rather than live.

The deferral was a documented gap, not an oversight. LIMITATIONS L4 named it,
STPA artefact 06 drew the `inference_cloud` edge as deferred, and ADR 0033
recorded it as the last classified-but-unregistered functional capability with
its supporting machinery already in place. The safety analysis already covers
the cloud edge: H-5 (cap exhaustion with no fallback) maps to SC-5, UCA-3a/3b
sit on the `inference_cloud` arc, and DR-5/DR-8 are the enforced mitigations.
This ADR is the promised follow-up. It decides to register the tool now that
the machinery behind it is built and pinned by tests.

## Decision

Register `inference_cloud` (T2) in `src/nous/tools/inference.py` as wiring over
existing seams. The handler builds an `InferenceFallback` whose cloud leg is the
capped `AnthropicClient.call`, whose local leg is `InferenceSubsystem.request_local`,
whose comms gate reads `engine.comms.derive_state()`, and whose cap gate reads
`anthropic_status.cap_status`. The ladder routes to the cloud when comms permit
and the cap is not exhausted, and degrades to the local mock otherwise, so the
controller always gets an answer (the H-5 no-fallback mitigation, realised at
the tool layer rather than only in the library). The response carries `path`,
`reason`, `cap_remaining`, and a `cap` snapshot so a degraded answer is legible.

The change touches no boundary surface. The cap and prompt-cache discipline in
`anthropic_client.py` are reused unchanged, and `policy.py` already classifies
`inference_cloud` as T2, so no policy edit is needed. The system slot defaults
to a short, stable, trusted instruction (stable so prompt-cache hits survive);
the operator `prompt` is the untrusted slot, consistent with the client's slot
discipline. `max_tokens` is clamped to a ceiling because a cloud token is a real
cost, while the daily cap remains the spend ceiling.

Two scope lines are drawn deliberately. First, `inference_request` (also
classified T2) stays deferred: the ladder inside `inference_cloud` already does
path-agnostic cloud-or-local routing, so a second verb adds no capability today,
and it remains an inert forward-classification consistent with the tier-coverage
test. Second, enriching the cloud call itself (adaptive thinking, streaming,
model-tier selection) is tracked as BL-069 and left out of this change so the
blast radius stays at tool wiring and the `anthropic_client.py` boundary is not
reopened.

## Consequences

A controller can now consume the cloud path through one audited tool and always
get an answer. DR-5's claim, that `inference_cloud` returns a structured cap
payload and the ladder routes to the local mock on cloud failure, becomes
literally true at the registered surface and gains an integration test
(`tests/integration/test_inference_cloud_tool.py`) alongside the existing
library-level pins. The tool surface grows by one (35 to 36).

The cost side is that the controller can now spend the daily cap, and real
money, where before only the local mock was reachable. The cap (ADR 0005) and
the `max_tokens` clamp bound this, and raising `NOUS_ANTHROPIC_DAILY_CAP`
remains an operator decision. Tests never reach the network: the autouse
key-scrubbing fixture covers the no-key degrade path, and the cloud-served and
cap-exhausted paths replace `AnthropicClient.call` with a fake.

Three alternatives were rejected. Enriching `call` with adaptive thinking and
streaming in the same change was rejected to keep the boundary file untouched
and the change small (deferred to BL-069). Registering `inference_request` as a
separate router was rejected as redundant under the ladder. Raising
`CapExhausted` to the controller instead of degrading was rejected because
SC-5 and H-5 require a fallback, which the ladder provides.

## Revisit triggers

Revisit if a controller needs the explicit cap-exhausted signal without a
local-mock fallback, which would argue for a distinct non-degrading verb. Revisit
when cloud-call quality demands adaptive thinking, streaming, or model selection,
at which point BL-069 lands and may touch `anthropic_client.py` under its own ADR.
Revisit if the local mock diverges far enough from real cloud behaviour that a
silently degraded answer misleads the controller, which would argue for a louder
degraded marker or for refusing rather than degrading.
