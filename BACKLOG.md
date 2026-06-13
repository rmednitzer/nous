# Audit Backlog (2026-06-13 full-pass)

Deferred items from the 2026-06-13 audit. This file is the audit's own
register; it does not replace the project's line-item `BL-NNN` tracker in
[`docs/backlog.md`](docs/backlog.md), which remains the home for feature work.
Each item links back to the findings register in
[`audit/02-security-findings.md`](audit/02-security-findings.md).

Schema per item: ID (finding) -- title -- severity -- effort -- rationale --
suggested approach -- dependencies -- suggested owner. Ordered by severity then
effort within each section.

## Security

### SEC-1 (S-03) -- Confine `scenario_load` to a scenarios directory

- Severity: Med. Effort: M.
- Rationale: T2 `scenario_load` accepts an unconfined caller path
  (`loader.py:85`), letting an authenticated controller read arbitrary host
  YAML and stamp attacker-chosen paths into the audit trail (CWE-22).
- Approach: per proposed [ADR 0042](docs/adr/0042-confine-scenario-load-to-a-directory.md):
  add `NOUS_SCENARIOS_DIR` (default `./scenarios`), resolve and confine at the
  tool boundary, leave the CLI library path untouched. Ship with a traversal
  test.
- Dependencies: ADR 0042 decision; config knob; tool-reference + runbook doc
  update.
- Owner: maintainer (touches the tool surface and config contract).

### SEC-2 (S-02) -- Constant-time OAuth token verification

- Severity: Med. Effort: M.
- Rationale: bearer/refresh/code lookups use a plain dict key
  (`oauth.py:227,336,359`), a non-constant-time present/absent timing leak
  (CWE-208). Theoretical given 384-bit tokens and network-latency dominance,
  but a best-practice gap on a credential surface.
- Approach: per proposed [ADR 0043](docs/adr/0043-constant-time-token-verification.md):
  verify the matched record with `hmac.compare_digest` and equalise the
  absent/mismatched paths. Regression test plus full OAuth suite re-run.
- Dependencies: ADR 0043 decision.
- Owner: maintainer (credential surface).

### SEC-3 (S-06) -- Defensive redirect_uri check in the OAuth provider

- Severity: Low. Effort: S.
- Rationale: `FileOAuthProvider.authorize` forwards `redirect_uri` without its
  own validation, relying entirely on the upstream MCP SDK check (CWE-601).
  Correct today; fragile if the SDK path is ever bypassed.
- Approach: validate the requested redirect URI against the client's registered
  set inside the provider as defense-in-depth.
- Dependencies: none.
- Owner: maintainer.

## Reliability

### REL-1 (S-04) -- Non-blocking daily-cap flock for multi-process

- Severity: Low. Effort: M.
- Rationale: `CallCap.increment` uses a blocking `fcntl.flock(LOCK_EX)` with no
  `LOCK_NB` (`anthropic_client.py:119`); a second process holding the lock would
  stall the asyncio event loop. No impact in the documented single-process
  model.
- Approach: only if multi-process is adopted -- `LOCK_NB` with bounded retry, or
  move the counter to a transactional store. Until then, document the
  single-process assumption next to the counter.
- Dependencies: a decision to support multi-process.
- Owner: maintainer.

### REL-2 (S-05) -- Optional bounded retry before cloud-to-local fallback

- Severity: Low. Effort: S.
- Rationale: a transient 429/5xx degrades straight to the local mock with no
  backoff (`inference_fallback.py`). Arguably by design (the ladder always
  returns an answer), but a single retry could keep more calls on the cloud
  path.
- Approach: one bounded retry on `429`/`503` with jittered backoff before
  degrading; keep the ladder as the terminal fallback.
- Dependencies: none.
- Owner: maintainer.

## Quality

### QUAL-1 (Q-FORMAT) -- Decide and enforce `ruff format`

- Severity: Low. Effort: S (mechanical, high-churn).
- Rationale: `ruff format --check` reports 80/172 files drifted; CI does not run
  it, so the tree is not format-clean and contributors can re-drift it.
- Approach: either add `ruff format --check` to the CI `check` job and reformat
  in one dedicated sweep commit, or document that formatting is intentionally
  unenforced. A proposed ADR (0044, not yet written) would record the choice.
- Dependencies: maintainer decision on whether to enforce.
- Owner: maintainer.

## Tooling

### TOOL-1 (Q-COV) -- Add coverage measurement

- Severity: Low. Effort: S.
- Rationale: no `pytest-cov` / `[tool.coverage]`, so coverage is unmeasured and
  blind spots cannot be quantified (current value `[UNVERIFIED]`). Test count
  and assertion density are high, but that is not the same as coverage.
- Approach: add `pytest-cov` to the dev extra, emit a non-gating coverage report
  in CI, establish a baseline, then consider a floor.
- Dependencies: none.
- Owner: maintainer.
