# ADR 0035: Enrich the cloud inference call

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0005 (Anthropic client and daily cap), ADR 0034 (cloud inference path)

## Context

ADR 0034 registered `inference_cloud` over the existing capped
`AnthropicClient.call` and deliberately left the call itself minimal: a plain
`messages.create` with cache-marked system blocks, the default model, and no
thinking or streaming. It named the enrichment (adaptive thinking, streaming,
model-tier selection) as BL-069 and drew the revisit trigger "when cloud-call
quality demands" it, "at which point BL-069 lands and may touch
`anthropic_client.py` under its own ADR." This is that ADR.

The `anthropic_client.py` boundary carries the cap and the prompt-cache
discipline the project depends on, so the enrichment is constrained: it must
not weaken the daily cap (ADR 0005), must keep the slot discipline (untrusted
operator content stays in the user slot), and must preserve the stable,
cache-marked system prefix so `cache_read_input_tokens` keeps registering hits.
A second constraint comes from the models the profile actually selects: the
default tier is Haiku 4.5 and the advanced tier is Sonnet 4.6. Adaptive thinking
and the effort parameter are not supported on Haiku 4.5, so sending a thinking
block to the default tier would fail the request rather than enrich it.

## Decision

Enrich `AnthropicClient.call` along three axes, each guarded so the default path
is unchanged.

Model-tier selection: `call` gains a `tier` argument ("default" or "advanced")
that resolves to `anthropic_model_default` / `anthropic_model_advanced`; an
explicit `model` still overrides. `inference_cloud` surfaces `tier` as a tool
parameter (validated, defaulting to "default") so a controller can ask for the
stronger model when a question warrants the spend.

Adaptive thinking, capability-guarded: when the resolved model supports adaptive
thinking (the Opus 4.6-and-later and Sonnet 4.6 families), `call` sends
`thinking={"type": "adaptive"}`; otherwise it omits the block. Because the
default tier is Haiku 4.5, the default cloud call is byte-for-byte the request
it was before, and only the advanced tier gains thinking. No sampling parameters
are sent (the 4.x families reject `temperature` / `top_p` / `top_k`), so the
request stays valid across tiers.

Streaming for long generations: when `max_tokens` exceeds a threshold, `call`
issues the request through `messages.stream()` and collects it with
`get_final_message()`, which keeps a long generation inside the request timeout;
shorter generations keep the single `messages.create`. Both paths run under
`with_options(timeout=...)` and extract only text blocks, so an adaptive-thinking
block never leaks into the returned answer. The client records
`usage.cache_read_input_tokens` from the response so the cache discipline is
observable (and pinned by a test) rather than assumed.

## Consequences

The cloud path can now reason harder on demand and stays robust on longer
answers, without reopening the cap or the slot discipline. The blast radius is
the one boundary file plus the tool that wires it; the tier guard means the
default tier behaves exactly as before, so no existing caller changes. The
registered tool surface is unchanged at thirty-six tools (the `inference_cloud`
schema gains an optional `tier` field, regenerated into
`docs/tool-reference.md`).

Tests never reach the network: a fake `AsyncAnthropic` exercises both the create
and stream paths, asserts the thinking block is present only for a
thinking-capable model, asserts every system block keeps its `cache_control`
marker, and asserts the surfaced `cache_read_input_tokens`. The daily-cap
behaviour from ADR 0005 is unchanged, so a cloud token is still bounded by the
cap and the `max_tokens` ceiling.

## Revisit triggers

Revisit if the default tier moves to a thinking-capable model, at which point
the capability guard could be retired and thinking enabled uniformly. Revisit if
a controller needs per-call control over thinking or effort independent of tier,
which would argue for surfacing those as explicit tool parameters. Revisit if the
streaming threshold proves wrong for real cloud latencies, or if the cloud
`max_tokens` ceiling is raised past the streaming requirement, in which case
streaming should become the default rather than a threshold branch.
