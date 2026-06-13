# Audit 03: Final Report (2026-06-13 full-pass)

- Date: 2026-06-13
- Revision baseline: `6e6d8127` (`origin/main` HEAD at start)
- Branch: `claude/nice-wozniak-py2l5n` (session-pinned; see audit 00 for the
  branch-name reconciliation)
- Scope: full audit, validation, targeted remediation, and documentation pass
  per the eight-phase mission.

## Executive summary

`nous` entered this audit in strong condition and leaves it slightly stronger.
The automated security surface is clean (pip-audit, bandit, gitleaks all zero),
the build is green (812 tests at baseline), and every quality gate the project
runs (`ruff`, `mypy --strict`, policy greps, `mkdocs --strict`) passes. The
repository already carries a deep, dated self-audit trail and 40 accepted ADRs,
so this pass focused on verifying the live state, probing the input boundaries
the prior audits had not exhaustively re-checked, and landing only changes that
are safe and locally testable.

One real defect was found and fixed: the Cursor-on-Target decoder's XXE guard
scanned only the first 512 bytes of a payload, so a `DOCTYPE`/`ENTITY`
declaration placed after a long comment bypassed the explicit refusal the
adapter advertised. The fix scans the whole payload and is pinned by a
regression test. Six further findings (two medium, four low/info) are
real-but-bounded and were deferred to the backlog with two proposed ADRs,
because they either change behavior (scenario-path confinement) or touch the
credential surface (constant-time token checks) and deserve a recorded
decision rather than a same-pass edit.

No critical or high-severity findings. No privilege-escalation, RCE, SQL
injection, secret exposure, or audit-bypass class of bug was found.

## Baseline vs post-fix metrics

| Metric | Baseline | Post-fix |
|--------|----------|----------|
| pytest | 812 passed, 0 failed | 813 passed, 0 failed |
| ruff check | clean | clean |
| mypy --strict | clean (162 files) | clean (162 files) |
| policy greps | pass | pass |
| mkdocs --strict | pass | pass |
| pip-audit | 0 vulns | 0 vulns |
| bandit | 0 issues | 0 issues |
| gitleaks | 0 leaks | 0 leaks |
| ruff format drift | 80 files (not CI-enforced) | 80 files (deferred, QUAL-1) |
| coverage | `[UNVERIFIED]` (no tooling) | `[UNVERIFIED]` (deferred, TOOL-1) |
| Security findings (open) | n/a | 0 critical, 0 high, 2 med, 3 low, 1 info (all backlogged) |

The single behavior change (CoT guard) added one test; the baseline suite was
re-run after it (`813 passed`).

## Commits (this pass)

1. `chore(audit): record recon inventory and validation baseline` -- Phase 0/1
   evidence (`audit/00-inventory.md`, `audit/01-baseline.md`).
2. `security: scan whole CoT payload for DOCTYPE/ENTITY, not first 512 bytes` --
   Phase 4 fix for finding S-01, plus a regression test (812 -> 813).
3. `chore(audit): record security and code-quality findings register` -- Phase
   2/3 register (`audit/02-security-findings.md`).
4. `docs(adr): propose scenario_load confinement and constant-time token checks`
   -- Phase 6 forward ADRs 0042, 0043 (Proposed); regenerated ADR index.
5. `docs(backlog): register deferred audit findings (2026-06-13)` -- Phase 7
   root `BACKLOG.md`.

(Phase 5 documentation pass found no drift to correct: STATUS.md already reads
812 at HEAD, the README quickstart executes clean end-to-end, and the docs
build strict. Verified, not edited.)

## Residual risk statement

Residual risk is low and well-characterised. The two medium findings (S-02
token-lookup timing, S-03 scenario path traversal) are bounded by, respectively,
384-bit token entropy under network-latency dominance, and T2 admission gating
with no content echo. Neither is remotely exploitable as it stands; both are
hardening opportunities with proposed ADRs awaiting a decision. The low/info
items are reliability nuances (flock under a hypothetical multi-process model,
transient-error retry) or SDK-delegated controls (redirect-URI validation,
PKCE) that are correct today and fragile only under changes the project would
control. Coverage is unmeasured, so unquantified test blind spots are the
largest unknown; test count and assertion density are high but are not a
substitute.

This audit did not hit any stop condition: the suite runs, no secret appears
actively exploited, no fix required a major bump or migration, and no embedded
repo content conflicted with the mission.

## Top 5 backlog items

1. **SEC-1 (S-03, Med)** -- confine `scenario_load` to a scenarios directory
   (proposed ADR 0042).
2. **SEC-2 (S-02, Med)** -- constant-time OAuth token verification (proposed
   ADR 0043).
3. **TOOL-1 (Q-COV, Low)** -- add coverage measurement to quantify blind spots.
4. **QUAL-1 (Q-FORMAT, Low)** -- decide and enforce (or document) `ruff format`.
5. **SEC-3 (S-06, Low)** -- defensive redirect_uri check in the OAuth provider.
