# ADR 0023: Audit cadence and regression-suite pattern

- **Status:** Accepted
- **Date:** 2026-05-24
- **Authors:** rmednitzer
- **Builds on:** ADR 0002, ADR 0007, ADR 0012

## Context

The repository has produced three point-in-time audits in five days:
the 2026-05-20 baseline in `AUDIT.md`, the 2026-05-23 delta audit (with
a same-day §10 re-audit after the catch-up merge train) in
`docs/audit-2026-05-23.md`, and the 2026-05-24 code-index audit in
`docs/audit-2026-05-24.md`. The cadence is not accidental: the L1
subsystem rollout, the live-MCP probe, and the cross-vendor regression
suite borrowed from a sibling simulator each surfaced a class of
finding that the prior audit run had not seen. The pattern emerged
faster than the convention that governs it.

The findings from each audit fall into three buckets. Some close
during the same merge train (C3 closed by the FastMCP lifespan PR, C6
closed by the policy-greps PR, N1 closed by the catch-up merge train).
Some stay open across multiple audits as carry-forward items (C2 flat
redaction, H6 OAuth lock, H7 family revocation, H8 rollback record,
H9 uncited inference values). Some are explicitly out of scope per
LIMITATIONS.md or by ADR-0004 design choice. Without a convention,
the three buckets blur, and the gap between "finding still open" and
"finding closed in code but not re-tested" is exactly where future
regressions land.

The borrowed `tests/regression/test_audit_findings.py` shows the
shape that closes the gap. Each class names one finding id (C1, C4,
C5, H3, M8), carries the prior defect in the class docstring, and
asserts the specific behaviour that closed it. A future change that
re-opens the finding fails in the regression suite with the original
bug summary already in scope, so the finding does not get
re-discovered from scratch. The pattern is the missing seam between
the audit reports (prose, point-in-time) and the test suite
(runtime, continuous).

The simulator's value proposition is legibility (`CLAUDE.md`,
"Repo purpose"). An audit that lands in a report and stays there is
illegible: a contributor cannot tell from the test suite which past
defects the project actively guards against. A regression class with
the prior bug in the docstring makes the audit history machine-readable.

## Decision

Three coupled conventions, effective from 2026-05-24:

1. **Audit cadence.** Produce a delta audit when (a) a sustained merge
   train lands and the surface visibly evolves (the L1 rollout drove
   the 2026-05-23 audit), (b) a cross-vendor pattern is borrowed and
   the porting touches the spine (the regression suite and the tick
   finiteness guard drove this audit), or (c) the calendar quarter
   crosses without an interim audit. Each audit lives at
   `docs/audit-YYYY-MM-DD.md` and is a *delta* against the immediately
   prior audit document; the 2026-05-20 baseline is the only
   "ground-up" audit. The delta format is fixed: executive summary,
   what closed, what remains open (re-verified each time), validation
   against documented standards, new observations, quality gates,
   recommended remediation order, out-of-scope. Each audit document
   cross-links to its predecessor and to the conformance documents
   under `docs/conformance/`.

2. **Regression-pin pattern.** When an audit finding closes in code,
   the same PR adds a class to `tests/regression/test_audit_findings.py`
   named after the finding id (`TestC1...`, `TestC4...`, etc.). The
   class docstring carries the prior defect in two paragraphs: what
   the bug was (with file and audit reference) and what the fix is.
   The class then asserts the specific behaviour that closed the
   finding. Findings that are still open are *not* represented; a
   class is added only after the fix lands. The regression suite is
   the canonical evidence that a finding is closed; the audit
   document records the fix, the regression class enforces it.

3. **Open-finding traceability.** The "open findings" table in each
   audit document re-verifies every still-open item against the
   current source, with a `file:line` reference. The remediation
   order is renumbered each audit so the next contributor reading
   the most-recent audit document sees the live plan without
   cross-referencing prior audits. The 2026-05-23 §10 re-audit and
   the 2026-05-24 audit both follow this convention; this ADR makes
   it explicit.

The conventions apply prospectively. Existing closed findings (C1,
C4, C5, H3, M8) were retroactively regression-pinned in PR #44; the
remaining code-level closures (C3 server lifespan, C6 CI policy
greps) should be pinned the next time the regression suite is
touched. N1 (deployment drift between the development line and
`main`) is a deployment-state finding rather than a code defect:
the closure evidence is a `git log` invariant (`origin/main`
matches `HEAD`), not an assertion that fits the unit-test surface,
so it is not regression-pinned. The cadence convention (this ADR's
first rule) is the durable guard against it re-opening.

## Consequences

Easier: a contributor reading the most-recent `docs/audit-YYYY-MM-DD.md`
sees the live remediation plan in one file, with `file:line`
references for every open finding. A change that re-opens a closed
finding fails in the regression suite with the original bug summary
already in scope, so triage starts from informed ground. The audit
history is machine-readable: the test class names map one-to-one
to the audit finding ids, and any audit document can be replayed
against the test tree to verify "is this finding actually closed in
code today" without re-reading every prior audit.

Harder: the regression file is now load-bearing for the audit
convention. A merge that drops a regression class drops the
guarantee that the corresponding finding stays closed. Reviewers
need to treat changes to `tests/regression/test_audit_findings.py`
the same way they treat changes to ADRs: deletions are deliberate
and require a justification in the commit message.

The audit cadence itself is a commitment. The project has produced
three delta audits in five days; the convention asks for at minimum
one per quarter (and one per substantial merge train). A quarter
that passes without a delta audit and without a merge train is a
quiet quarter, and the absence itself is a finding the next audit
should explain. If the cadence drops, the convention should be
revisited rather than silently relaxed.

Alternatives rejected:

- **One ground-up audit per release, no deltas.** Drops the cadence
  and the regression-pin signal. A finding closed mid-cycle stays
  invisible until the next ground-up sweep.
- **Regression cases interleaved with the rest of the test suite.**
  The audit-finding cases are deliberately segregated under
  `tests/regression/` so a contributor can find them by name. A
  bug-driven test scattered among unit tests for the same module is
  not discoverable as "the test that pins audit finding C4".
- **No regression-pin, the audit document is the source of truth.**
  Today's pattern. The 2026-05-20 audit had C5 (estimator
  covariance) closed for two days before the regression class
  surfaced the asymmetry between "fixed in code" and "guarded in
  tests." The regression-pin is the cheapest way to make the
  difference observable.

The audit cadence and the regression-pin pattern together close the
gap that ADR 0007 (additive-surface rule beyond L0) leaves open: ADR
0007 governs how new surface lands, this ADR governs how prior
defects stay closed. The two are complementary.

## Revisit triggers

- The regression-pin file grows beyond 50 classes. The pattern was
  optimised for the current scale (five classes); at much larger
  scale a per-finding directory layout or a per-area split may
  become necessary.
- An audit finding requires evidence that does not fit a unit-style
  assertion (for example, a multi-hour soak test or a hardware-in-the-loop
  measurement). Such findings need a different closure surface; the
  regression-pin pattern would mislead by suggesting the finding is
  closed at the unit level when it is not.
- The cadence drops below one audit per quarter for two consecutive
  quarters. This is a signal either that the project has stabilised
  past the point where deltas add value (revise the convention to a
  longer interval), or that audits have become a chore rather than a
  signal (revise the surface to make audits cheaper).
- A regulator or conformity-assessment body asks for the audit
  history as evidence. The convention should align with whatever
  artefact format the body accepts; today the markdown delta format
  is internal-facing only.
