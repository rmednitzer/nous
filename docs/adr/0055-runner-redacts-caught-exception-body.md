# ADR 0055: Redact the runner's caught-exception body to the exception class

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0048 (runner exit_code), BL-078 (device_info persistence redaction)

## Context

`runner.run` wraps every MCP tool call. When the wrapped work coroutine raises,
the runner catches it and returns a body to the caller. That body was
`f"[error {exc.__class__.__name__}: {exc}]"`: the raw `str(exc)`, truncated to
the output budget but never redacted. Several T0 reads reach the database.
`state_get` and `state_history` query SQLite or, under `NOUS_DB_URL`, Postgres
or MySQL, and a connection-time or query-time failure on one of those backends
raises an exception whose message can carry the data source name, including the
host, user, and password embedded in the URL. So a caller of a read-only tool
could read a credential out of an error body.

The project already guards this exact leak everywhere else a backend error
surfaces. The server's database init path (BL-078) reduces an `init_db` failure
to `exc.__class__.__name__` for the `device_info.persistence` block and writes
the full `class: message` to stderr, and the audit sink logs a degraded write as
the class name only. The runner's caught-exception path was the one remaining
surface that returned the message verbatim, and it sits on every tool call.

## Decision

The caught-exception body is now `f"[error {exc.__class__.__name__}]"`: the class
name, no message. The full detail (`class: message`) is echoed once to stderr,
wrapped in `contextlib.suppress(Exception)` so a logging failure can never turn
into a second fault on the error path, mirroring the server's DB-init handler.
The audit record is unaffected in information content: it only ever stored the
body's SHA-256, never the body, so no error text moves across a trust boundary
that it did not already cross.

The ADR 0048 contract is unchanged. A caught error still stamps `exit_code=1`
with `denied=False`, so a consumer separates a worker error from a normal return
(`exit_code` None) and from a policy refusal (`denied` True) on the typed fields,
not the body string. The prefix stays `error <class>`, which is what
`skills/nous-troubleshooting.md` already tells an operator to read.

## Consequences

A message-borne secret can no longer reach an MCP caller through the runner. An
operator with host access keeps the full exception on stderr or the journal for
debugging, the same place the DB-init and audit-degraded details already go. The
class name is enough to route to the right `*_status` read, which is all the
troubleshooting runbook asked of the prefix.

The cost is that a caller no longer sees the exception message inline and must
correlate with the server log for detail. That is the intended trade: the inline
message is the field that can carry a credential.
`tests/regression/test_audit_findings.py` pins a credential-shaped message and
asserts it does not appear in the returned body while the class name and the
`exit_code=1` contract survive. Closes BL-090 (audit 2026-06-14b HIGH-1).

## Revisit triggers

Revisit if a controller genuinely needs structured error detail inline (then add
a redacting formatter that strips URL credentials and bounded PII rather than
returning the class alone), or if a future tool surfaces a non-`Exception`
failure mode the catch does not cover.
