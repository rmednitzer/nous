# Bandit `# nosec` suppression catalog

Closes AUDIT-2026-05-27 N17. Every inline `# nosec` annotation in
`src/nous/` is listed here with its rationale, the prior threat the
suppression rules out, and the canonical test or document that
backs the disposition. A reviewer reading the CI output can verify
that every suppression is principled rather than expedient without
chasing each annotation back through the source tree.

The supply-chain CI job (`bandit -r src/nous`, configured in
`.github/workflows/ci.yml`) runs the full ruleset. A new
suppression must land in the source tree *and* be added to this
catalog in the same PR. A bandit finding without a corresponding
entry here is a CI failure regardless of severity.

## Catalog

### B106 -- hardcoded password

| Location | Annotation | Rationale |
|----------|------------|-----------|
| `src/nous/auth/oauth.py:289` | `token_type="Bearer"` | OAuth 2.1 token type literal per RFC 6750 §6.1.1. Bandit treats the string `"Bearer"` as a hardcoded credential because it appears as a keyword argument; in context it is the token-type discriminator that tells the client how to use the access token. The actual credential is `access_token=access`, which is freshly minted by `secrets.token_urlsafe(48)` on the line above. |

### B314 -- ElementTree.XMLParser

| Location | Annotation | Rationale |
|----------|------------|-----------|
| `src/nous/interop/cot.py:109` | `parser = ElementTree.XMLParser()` | The decoder is XXE-safe by construction: the `_safe_parse` function explicitly refuses any payload that starts with `<!DOCTYPE` or `<!ENTITY` in the first 512 bytes before invoking the parser. CPython's `ElementTree.XMLParser` does not resolve external entities by default; the doctype refusal defends against a future contributor who swaps in a different parser. The behaviour is regression-pinned at `tests/regression/test_audit_findings.py::TestH3CotEventCarriesRequiredAttributes::test_decoder_refuses_doctype` and documented in `docs/conformance/cot-tak.md`. |

### B405 -- import xml.etree

| Location | Annotation | Rationale |
|----------|------------|-----------|
| `src/nous/interop/cot.py:25` | `from xml.etree import ElementTree` | Same defense as B314: the imported module is only invoked through `_safe_parse`, which refuses doctype and entity declarations before parsing. The suppression scopes the bandit check to "do not flag this import alone"; the call sites still need the B314 suppression on the parser instantiation. |

### B406 -- import xml.sax

| Location | Annotation | Rationale |
|----------|------------|-----------|
| `src/nous/interop/cot.py:26` | `from xml.sax.saxutils import escape, quoteattr` | The `escape` and `quoteattr` helpers serialise output (encoder side), they do not parse untrusted input. Bandit's B406 rule flags any import of `xml.sax.*` on the assumption that the program will parse XML; in this codebase the only XML-parsing path runs through `_safe_parse` (above). The encoder needs the escape helpers to produce well-formed CoT XML; replacing them with manual string concatenation would introduce its own injection risk. |

## How to add or remove a suppression

A new `# nosec <code>` annotation in `src/nous/` lands as part of
the PR that introduces the flagged code. The PR description
includes:

1. The bandit code and severity.
2. The threat the rule catches in the general case.
3. Why the threat does not apply here (the regression test, the
   conformance document, or the structural argument).
4. A row appended to the catalog above.

Removing a suppression is the reverse: drop the annotation, drop
the catalog row, and verify the bandit job passes on the cleaned
source. If bandit flags the line again, either the threat returned
(treat as a real finding) or the upstream rule changed shape
(update the annotation or escalate via a Bandit issue).

## Cross-references

- `SECURITY.md` -- reporting policy and hardening posture.
- `.github/workflows/ci.yml` -- the `supply-chain` job that
  enforces zero bandit findings.
- `docs/conformance/cot-tak.md` -- XXE posture for the CoT
  adapter.
- `tests/regression/test_audit_findings.py` -- regression pins
  for the closed audit findings.
- ADR 0023 -- audit cadence and regression-suite pattern.
