# Audit 02: Security and Code-Quality Findings Register

Date: 2026-06-13. Revision audited: `6e6d8127`. Read-only collection; the
single safe local remediation landed in a separate commit and is marked
`Fixed` below.

Methodology: ecosystem-native dependency audit (pip-audit), SAST (bandit),
secret scanning (gitleaks, full history), plus a manual OWASP-oriented review
of every external input boundary (interop parsers, the OAuth issuer, the DB
layer, YAML/config loading, network calls, and subprocess/eval surfaces).
semgrep was not available in the environment; the manual boundary pass stands
in for it and is recorded with file:line evidence.

## Automated tooling results

| Tool | Command | Result |
|------|---------|--------|
| pip-audit | `pip-audit --strict --no-deps -r <exported reqs>` | 0 known vulnerabilities (175 pinned reqs) |
| bandit | `bandit -r src/nous` | 0 issues, all severities/confidences; 0 `#nosec` net of documented XML markers |
| gitleaks | `gitleaks detect --redact` | 0 leaks across 49 commits (full history) |

No dependency CVEs, no committed secrets, no SAST hits. The lockfile is
internally consistent and all GitHub Actions are SHA-pinned (`ci.yml`,
`docs.yml`); the CI workflow sets `permissions: contents: read` at workflow
scope. Dockerfiles are absent (deployment is systemd + Caddy on a VM); the
systemd units run as a dedicated non-root user (see `deploy/`), reviewed for
hardening in audit 03.

## Findings register

Schema: ID, severity, CWE, file:line, evidence, exploit-plausibility,
recommended fix, effort (S/M/L), disposition. IDs are prefixed `S-`
(security) and `Q-` (quality, audit 03 appends here too).

### S-01 (was 1-A) -- Med -- CWE-611/CWE-776 -- `src/nous/interop/cot.py:113`

Evidence (pre-fix): the XXE guard scanned only `payload[:512]`
(`if b"<!DOCTYPE" in payload[:512] ...`). Verified by inspection and by a
one-shot check: a `<!DOCTYPE>` placed after a 609-byte comment was missed by
the old slice (`old guard caught: False`) but is a valid position for an XML
internal subset, so it reached `ElementTree.XMLParser`.

Exploit plausibility: low immediate impact (CPython stdlib `xml.etree` does
not resolve external entities by default, so no SSRF/file read), but the
adapter advertised an explicit DOCTYPE-refusal guarantee it did not uphold,
and the guarantee is the only thing standing between a future parser swap and
an XXE/billion-laughs regression.

Recommended fix: scan the whole payload. Effort: S.

Disposition: **Fixed** (commit `security: scan whole CoT payload ...`).
Whole-payload scan plus a regression test that places the DOCTYPE past byte
512. 812 -> 813 pytest pass.

### S-02 (was 3-A) -- Med -- CWE-208 -- `src/nous/auth/oauth.py:227,336,359`

Evidence: bearer/refresh/authorization-code lookups resolve the
caller-supplied secret as a plain dict key (`rec = tokens.get(token)`,
`codes.get(authorization_code)`), which is not a constant-time comparison.

Exploit plausibility: theoretical. Tokens are 384-bit `secrets.token_urlsafe`
values, and over-network latency dominates the dict-lookup timing delta, so a
remote timing oracle distinguishing "present" from "absent" is not practically
realisable. The MCP SDK already uses `hmac.compare_digest` for the client
secret. This is a best-practice gap on a credential surface, not an exploitable
hole.

Recommended fix: after the dict lookup, confirm the match with
`hmac.compare_digest(candidate, stored)`, or document the accepted risk.
Constant-time storage for a dict-backed store is awkward, so this warrants a
deliberate decision. Effort: M.

Disposition: **Backlog** (BACKLOG SEC-1, proposed ADR 0042). `oauth.py` is a
credential surface; the change deserves an ADR and is not a same-pass fix.

### S-03 (was 5-A) -- Med -- CWE-22 -- `src/nous/scenarios/loader.py:85`, `src/nous/tools/scenarios.py`

Evidence: `load_scenario_file` does `p = Path(path).expanduser()` with no
`.resolve()` and no confinement check; the T2 `scenario_load` tool passes a
caller-supplied `path` straight through. An authenticated T2 caller can point
the loader at any readable file on the host.

Exploit plausibility: medium-low. Reading is gated behind T2 admission
(privileged), and most non-YAML files yield an empty/default `Scenario` after
Pydantic validation, so the file contents are not echoed back; the path string
is, however, recorded in the audit trail, and a crafted YAML (large
`tick_budget` with many steps) is a resource-exhaustion vector in the runner.

Recommended fix: resolve the path and confine it to a configured
`NOUS_SCENARIOS_DIR` (default `./scenarios`), rejecting escapes. This is a
behavior change (absolute paths used by the CLI today would need the directory
allowance), so it needs a test and a decision rather than a silent clamp.
Effort: M.

Disposition: **Backlog** (BACKLOG SEC-2, proposed ADR 0043). Deferred to avoid
breaking the documented `nous scenario <path>` CLI workflow without an ADR.

### S-04 (was 2-A) -- Low -- CWE-833 -- `src/nous/anthropic_client.py:107-153`

Evidence: `CallCap.increment` acquires `fcntl.flock(LOCK_EX)` with no
`LOCK_NB`. Under the asyncio single-thread model, a blocking flock held by a
*second process* would stall the entire event loop.

Exploit plausibility: none in the documented single-process deployment; this
is a reliability note for a hypothetical multi-process model. The current code
is correct for its stated scope.

Recommended fix: if multi-process is ever adopted, use `LOCK_NB` with a bounded
retry, or move the counter to a transactional store. Effort: M.

Disposition: **Backlog** (BACKLOG REL-1). No change now.

### S-05 (was 2-B) -- Low -- CWE-703 -- `src/nous/inference_fallback.py`

Evidence: a transient cloud error (429/5xx) is caught by the fallback ladder
and degrades immediately to the local mock with no backoff/retry.

Exploit plausibility: not a security issue; an availability/quality nuance. The
ladder is the intended degradation path (always return an answer), so this is
arguably by design.

Recommended fix: optional single bounded retry on `429`/`503` before
degrading. Effort: S. Disposition: **Backlog** (BACKLOG REL-2). No change now.

### S-06 (was 3-B) -- Low -- CWE-601 -- `src/nous/auth/oauth.py:193-204`

Evidence: `FileOAuthProvider.authorize` stores and forwards
`params.redirect_uri` with no own validation; redirect-URI validation happens
upstream in the MCP SDK (`client.validate_redirect_uri`) before the provider
is called.

Exploit plausibility: low. Correct as written (SDK validates first); only
reachable if the SDK layer is bypassed by a direct provider call.

Recommended fix: add a defensive redirect-URI check in the provider against the
registered set. Effort: S. Disposition: **Backlog** (BACKLOG SEC-3).

### S-07 (was 3-C) -- Info -- CWE-1104 -- `src/nous/auth/oauth.py:192`

Evidence: PKCE (`S256`) is verified by the MCP SDK token handler, not by the
application; the provider only stores `code_challenge`.

Exploit plausibility: none today. Risk is a silent loss of PKCE enforcement if
the SDK is downgraded to a version that relaxes it.

Recommended fix: pin a minimum `mcp` version that enforces PKCE (already
`mcp>=1.27`) and add a conformance note. Effort: S. Disposition: **Noted**;
covered by the existing lower bound. No backlog item.

## Confirmed-safe surfaces (defense-in-depth already present)

These were checked and found correctly hardened; recording them so a future
pass does not re-flag them.

- XML (CoT): stdlib `xml.etree` (no external-entity resolution by default) plus
  an explicit DOCTYPE/ENTITY refusal (now whole-payload) and full
  `saxutils.escape`/`quoteattr` on the encode side. No `defusedxml` required.
- Binary KLV (`misb_klv.py`): key range and value length bounded, BER length
  checked against the buffer before slicing -- no OOB read.
- NMEA (`nmea0183.py`): non-ASCII rejected, checksum validated.
- JSON adapters (`stanag_4774.py`, `sensorthings.py`): payload length capped
  (64 KiB) before `json.loads` -- large-allocation DoS closed.
- YAML: `yaml.safe_load` everywhere; no `yaml.load` on untrusted input.
- SQL (`db.py`): 100% SQLModel/SQLAlchemy ORM; `n` clamped to `[1,1024]`; no
  raw string interpolation. The `session.exec` is the ORM method, not builtin
  `exec`.
- Tokens: `secrets.token_urlsafe` throughout; no `random` for security material.
- OAuth state files: atomic `O_TRUNC`+`fsync`+rename, `0o600`, parent-dir fsync.
- Audit redaction: recursive across nested maps/lists with per-depth truncation
  (`audit.py:95-127`); output bodies are hashed, never written to disk.
- Daily cap: write+`fsync` under `flock` before release; corrupt counter
  refuses the call rather than resetting (`anthropic_client.py:118-153`).
- Cloud calls: per-call SDK timeout (`with_options(timeout=...)`), `max_tokens`
  ceiling (4096) at the tool layer, streaming over 1024 tokens.
- Config: Pydantic `BaseSettings`, fail-fast validators, `frozen=True`.
- No `subprocess`/`os.system`/`eval`/`exec` in application code.

## Phase 3: code-quality findings (Q-)

The quality pass found the codebase in strong shape: no `TODO`/`FIXME`/`XXX`/
`HACK` markers in `src/` (`grep -rnE` empty), no `httpx`/socket network surface
in application code (it is a simulator), 1,655 assertions across the test tree,
no assertion-free `test_*.py` files, and the only skip markers are conditional
`skipif(shutil.which("git") is None)`. The bare `except Exception` sites in
`runner.py:77` and `audit.py:499` are intentional and documented (a tool call
or an audit write must never crash the server); both are narrow and re-raise
nothing silently -- they record the failure. Not findings.

### Q-FORMAT -- Low -- repository-wide -- `ruff format` drift

Evidence: `uv run ruff format --check .` reports 80 of 172 files would be
reformatted. CI does not run `ruff format --check` (the `check` job is lint +
typecheck + test only), so this is not a CI break, but the tree is not
`ruff format`-clean. A blanket reformat touches 80 files with no behavior
change (large blast radius, noisy diff). Recommended approach: either add
`ruff format --check` to CI and reformat in one dedicated sweep, or document
that formatting is not enforced. Effort: S (mechanical) but high-churn.
Disposition: **Backlog** (BACKLOG QUAL-1, proposed ADR 0044). Not executed in
this pass to keep the audit diff reviewable.

### Q-COV -- Low -- tooling -- no coverage measurement configured

Evidence: no `pytest-cov` in the dev extra, no `[tool.coverage]` /
`.coveragerc`. Coverage was not measurable this pass; the percentage is
`[UNVERIFIED]`. Test *count* and assertion density are high, but blind spots
cannot be quantified. Recommended approach: add `pytest-cov` to the dev extra
and a non-gating coverage report in CI (gate later once a baseline is known).
Effort: S. Disposition: **Backlog** (BACKLOG TOOL-1).

### Q-PYVER -- Info -- environment -- local interpreter below floor

Evidence: the host interpreter is CPython 3.11.15 while `requires-python =
>=3.12` and CI pins 3.14. `uv run` masks this by provisioning the resolved
3.12+ venv, so no target broke. Recorded for transparency; no action.
Disposition: **Noted**.
