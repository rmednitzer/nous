# ADR 0043: Constant-time verification for OAuth bearer and refresh tokens

- **Status:** Proposed
- **Date:** 2026-06-13
- **Authors:** rmednitzer
- **Builds on:** ADR 0001

## Context

The file-backed OAuth issuer resolves a presented bearer, refresh, or
authorization-code secret by using it directly as a dictionary key:
`rec = tokens.get(token)` (`src/nous/auth/oauth.py:227,336,359`). A dict lookup
is not a constant-time operation, so it leaks, through timing, whether a
presented token is present in the store. The 2026-06-13 audit logged this as
finding S-02 (CWE-208, observable timing discrepancy).

The practical risk is low. Tokens are 384-bit `secrets.token_urlsafe(48)`
values, and over-network latency dominates the nanosecond-scale dict-lookup
delta, so a remote oracle distinguishing "present" from "absent" is not
realistically achievable. The MCP SDK already compares the client secret with
`hmac.compare_digest`. This is a best-practice gap on a credential surface
rather than an exploitable hole, which is why it is a deliberate decision and
not a same-pass fix: a dict-backed store cannot be made fully constant-time
without changing the storage model, so the question is how much hardening is
worth the complexity.

## Decision

Proposed: keep the dict store, but verify the matched record's token field
against the presented secret with `hmac.compare_digest` before returning it,
and structure the lookup so the "absent" and "present-but-mismatched" paths do
the same comparison work. This closes the present/absent timing distinction at
the comparison step without rebuilding the store. The full constant-time-store
alternative (keyed by a fixed-length HMAC of the token, comparing tags) is
recorded as the heavier option to revisit only if the threat model changes to
include a local high-precision attacker.

## Consequences

The token-load path gains a constant-time comparison and stops advertising
present/absent through timing, aligning the application layer with the SDK's
client-secret handling. The cost is marginal latency per token load and a small
amount of added code on a high-blast-radius surface, so the change ships with a
regression test that asserts the comparison path and re-runs the OAuth suite.

Rejected for now: re-keying the store by HMAC tag. It is the more complete
defense but is disproportionate to a threat dominated by network latency.

## Revisit triggers

Revisit if the issuer is ever exposed to a co-located (same-host) untrusted
client, if token entropy is reduced, or if a multi-tenant L3 deployment widens
the credential surface.
