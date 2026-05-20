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
  by Alembic; the v0.1 baseline ships two tables (`state_transitions`,
  `audit_entries` as a mirror of the JSONL log).
- Audit records live in a *separate* JSONL file at
  `$NOUS_HOME/audit.jsonl`. The handler is a `WatchedFileHandler` so
  rotation does not break the file descriptor. On Linux, the operator
  is encouraged to make the file append-only with `chattr +a` and rotate
  it with the bundled `deploy/logrotate.conf`.

## Consequences

Easier: backups copy a directory. Audit ships as one file. Migrations
follow Alembic conventions.

Harder: two stores must stay in sync if a downstream consumer expects a
single source of truth for "what happened". The SQLite mirror of the
audit log is deliberately a *subset* of the JSONL record.

Alternatives rejected:

- Postgres. Operational weight too high for a single-VM simulator.
- One JSONL log for everything. State queries would be linear scans.

## Revisit triggers

- Multi-host deployment becomes a requirement.
- Audit query latency on a large file becomes a bottleneck.
- A regulator asks for a tamper-evident chain over the audit (then
  enable the optional daily hash chain, BL-031).
