# ADR 0057: Authorize the breaking rename of tick_advance's count fields

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0007, ADR 0040

## Context

The 2026-06-14b audit's MED-2 finding showed that `tick_advance` returned a
single `ticks_advanced` field set to the requested count `n`, while the engine's
`tick` and `ts_s` in the same payload reflected the true advance. The two
disagree whenever the live tick loop (ADR 0040) fires its own `engine.tick()`
during the periodic checkpoint yield the advance performs every 50 ticks: a
controller computing `start_ts + ticks_advanced * dt` then contradicts the
`ts_s` the same call reported. An honest contract needs two numbers, not one:
the ticks this call stepped, and the net engine advance.

The clear fix replaces `ticks_advanced` with `ticks_requested` (the stepped
count, `n`) and `ticks_elapsed` (the net advance, `state.tick - start_tick`).
But `tick_advance` is part of the MCP tool surface, which ADR 0007 designates an
external contract: from L1 onward a rename or removal on that surface is a
breaking change that an ADR must authorize. Renaming `ticks_advanced` out of
existence is exactly such a break.

An additive alternative exists (retain `ticks_advanced` as a deprecated alias
equal to the net advance, and add the two new fields). It was considered and
rejected: keeping a field whose name the audit found misleading, solely for
compatibility, perpetuates the ambiguity the finding is about, and the alias
would duplicate `ticks_elapsed` for every caller indefinitely. The surface is
young and no external consumer pins `ticks_advanced` today, and the one
deployment that already observed the field (the stateless HTTP server) runs no
tick loop, so its `ticks_advanced` already equalled the net advance: the break
is invisible there, and only the buggy concurrent-loop reading changes.

## Decision

The rename is authorized as a breaking change to the `tick_advance` output
contract. The result drops `ticks_advanced` and reports `ticks_requested` (the
ticks this call stepped) and `ticks_elapsed` (the net engine advance) as
distinct fields; `tick` and `ts_s` remain the resulting absolute state, so
`ts_s` tracks `ticks_elapsed`. The CHANGELOG carries a `BREAKING CHANGE` note
naming the dropped field and its replacements, satisfying the ADR 0007
requirement that a surface break ship with a paired ADR and an honest release
note. No other tool's output is touched, and `tick_advance`'s input signature
(the `n` parameter, its `[1, 600]` bound, the T1 tier) is unchanged.

## Consequences

A controller now reads an unambiguous pair: what it asked for and what the
engine actually did, with `ts_s` consistent with the latter. The cost is a
one-time break for any consumer that parsed `ticks_advanced`; that consumer sees
a `KeyError` rather than a silently wrong number, which is the safer failure.
Closes BL-093 (the code, tests, and the MED-2 regression pin landed with the
finding); this ADR records the contract decision the rename required.

## Revisit triggers

A future tool-output change that cannot be expressed additively should cite this
ADR as precedent for the break-plus-ADR path, or the project may decide at v1.0
to freeze tool outputs as strictly as inputs, at which point a rename like this
one would instead require a deprecation window.
