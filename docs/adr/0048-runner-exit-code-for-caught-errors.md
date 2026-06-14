# ADR 0048: Stamp the audit exit_code on the runner's caught-exception path

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0001, ADR 0002

## Context

The audited runner (`runner.run`) writes one audit record per tool call, and the
record carries an `exit_code: int | None` alongside a `denied: bool`. The M1 fix
(AUDIT-2026-05-20) stamped `exit_code=1` on the policy-denial path so an operator
can count denials per tier per day without parsing the body string, and its
docstring framed the intent plainly: a consumer splits on `exit_code is not
None` to bucket denials and worker errors apart from normal returns.

The runner's caught-exception path never actually held up that intent. A tool
whose `work()` raised was caught, its body set to `[error ClassName: detail]`,
and the audit record written with `exit_code` defaulting to `None`, identical to
a normal return. The 2026-06-14 audit (RUN-1) found that a consumer therefore
cannot distinguish a caught worker error from a normal tool result on the typed
field, only by string-matching the `[error ...]` body prefix, which is exactly
the brittleness the M1 fix set out to remove. An existing test even pinned the
gap, asserting `exit_code is None` on the exception path.

## Decision

Stamp `exit_code=1` on the runner's caught-exception path, the same code the
denial path uses. The audit `exit_code` now carries a two-value contract: `None`
for a normal tool return, and `1` for any abnormal outcome (a policy refusal or a
caught worker exception). The existing `denied` boolean discriminates the two
abnormal classes: `denied=True` is a policy refusal, and `denied=False` with
`exit_code=1` is a caught worker error.

The change is four lines in `runner.py`: track whether `work()` raised and pass
`exit_code=1 if error else None` into the single post-work audit write. The body
mapping, the truncation budget, the redaction allowlist, and the BL-016 hash
chain are untouched, and the denial path keeps its existing `exit_code=1`. The
test that pinned the old `None` is updated to assert `1`.

## Consequences

A JSONL consumer can now classify every audit line on typed fields alone:
`(denied=False, exit_code=None)` is a normal return, `(denied=True,
exit_code=1)` is a denial, and `(denied=False, exit_code=1)` is a caught worker
error. The M1 fix's stated invariant becomes true rather than aspirational, so
counting tool failures for an SLO, or alerting on a spike of worker errors
distinct from policy friction, no longer requires parsing the `[error ...]` body
prefix.

The cost is a contract change on a high-blast surface. A consumer that had
learned to treat `exit_code=None` as "the call reached the tool" must now read
`denied` and `exit_code` together. The change is additive in spirit (a field
that was always `None` on the error path now carries a value), and the only
in-repo consumer is the test suite, updated here.

Alternatives rejected. A distinct exit_code for worker errors (for example `2`)
would duplicate the `denied` flag, which already separates a refusal from a
caught error, so the two-value contract is the smaller, sufficient change.
Leaving the exception path at `None` and documenting the body-prefix convention
is the brittleness M1 set out to remove; encoding the outcome in a typed field
is the point of the audit schema. Re-raising the exception instead of catching
it would break the runner's contract (ADR 0001) to return one bounded string and
never let a tool fault break the MCP response; the catch stays, only the audit
stamping changes.

## Revisit triggers

- A consumer needs to distinguish worker-error classes (timeout versus value
  error versus ...) on the audit field, which would justify a richer exit_code
  taxonomy or a dedicated error-class field.
- The runner grows a third successful outcome (for example a partial or streamed
  result) that the two-value exit_code cannot express.
