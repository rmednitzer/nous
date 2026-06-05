# ADR 0002: SQLite with Alembic, JSONL audit alongside

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001

## Context

The simulator persists two kinds of state: structured state-machine
transitions and tick samples (queryable, joinable, evolving), and audit
records (append-only, ship-off-host, no body bytes). One database for
both is convenient until the audit log has to be hardened against
modification; two stores keep the contracts crisp.

The deployment target is a single VM, not a cluster. SQLite with WAL
gives us read-during-write, atomic transactions, and a file we can back
up by copying.

## Decision

- Structured state lives in SQLite at `$NOUS_HOME/state.db`, opened with
  `PRAGMA journal_mode=WAL` and `synchronous=NORMAL`. Schema is managed
  by Alembic; the v0.1 baseline ships two tables: the live `state_transitions`,
  and `audit_entries`, reserved for a future JSONL mirror (it was never wired;
  see the 2026-06-05 update below).
- Audit records live in a *separate* JSONL file at
  `$NOUS_HOME/audit.jsonl`. The handler is a `WatchedFileHandler` so
  rotation does not break the file descriptor. On Linux, the operator
  is encouraged to make the file append-only with `chattr +a` and rotate
  it with the bundled `deploy/logrotate.conf`.

## Consequences

Easier: backups copy a directory. Audit ships as one file. Migrations
follow Alembic conventions.

Harder: two stores would have to stay in sync if a downstream consumer
expected a single source of truth for "what happened". That sync burden is
why the `audit_entries` mirror was left reserved rather than wired (see the
update below); the JSONL record is the single audit source today.

Alternatives rejected:

- Postgres. Operational weight too high for a single-VM simulator.
- One JSONL log for everything. State queries would be linear scans.

## Revisit triggers

- Multi-host deployment becomes a requirement.
- Audit query latency on a large file becomes a bottleneck.
- A regulator asks for a tamper-evident chain over the audit (then
  enable the optional daily hash chain, BL-031).

## Update (2026-06-05, BL-065)

This ADR specified `audit_entries` as a mirror of the JSONL log, but the
mirror was never wired: nothing instantiates `AuditEntry`, so the live audit
trail is the JSONL sink alone (AUDIT-2026-06-01 N19). The decision is to leave
the table **reserved**, not to wire a second audit surface.

The JSONL record is already append-only, ships off-host, and carries the
BL-016 hash chain and the BL-031 daily anchor. A live SQLite mirror would
reintroduce the sync burden noted under Consequences and add a second tamper
surface to protect, with no current consumer: the audit tools (`audit_verify`,
`audit_summary`) read the JSONL, and only `state_transitions` is queried from
SQLite. Wiring the mirror would also touch the audit path, a high blast-radius
surface, for no present need.

The schema stays in the Alembic baseline so the table is ready. The revisit
trigger is a controller that needs SQL queries over the audit: at that point
the mirror is wired carrying `prev_hash` / `entry_hash` so both surfaces
verify against the same chain. `AuditEntry` carries a docstring marking it
reserved, and `tests/unit/test_audit_entries_reserved.py` pins that the live
audit path does not write the table.
