# ADR 0037: Schema migration workflow

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0002 (persistence), BL-015 (Alembic baseline)

## Context

BL-015 introduced Alembic with an idempotent baseline
(`alembic/versions/0001_baseline.py`) and an `env.py` that resolves the
database URL from `-x url=`, then `NOUS_DB_URL`, then the `alembic.ini` default.
`init_db()` also creates the tables through `SQLModel.metadata.create_all` for
developer ergonomics on first boot. What BL-051 found missing was the last
mile: a project-standard entry point for running a migration against the
deployment database, and a test pinning that the migration path actually
produces the schema. An operator was left to invoke `alembic` by hand and
remember to point it at the right URL, and nothing exercised
`alembic upgrade head` in CI.

## Decision

Add `scripts/migrate.py` as the project-standard migration entry point. It
builds an Alembic `Config` from `alembic.ini`, pins `script_location` to the
repository's `alembic/` directory (so it works from any working directory),
and sets `sqlalchemy.url` to the engine's own `Settings.resolved_db_url()`
(`NOUS_DB_URL`, or the `$NOUS_HOME` sqlite default). It dispatches
`upgrade` / `downgrade` / `current` / `history` / `revision` / `stamp` through
`alembic.command`. So `scripts/migrate.py upgrade` hits the same database the
server reads, with no URL to remember.

Alembic remains the single source of truth for the schema. `init_db` stays a
developer convenience for first boot: it `create_all`s the current metadata,
which the idempotent baseline tolerates (a deployment that booted before
Alembic was adopted already has the tables, and the baseline skips them). A
controller never runs migrations; this is an operator or CI action, so the
runner lives in `scripts/`, not on the MCP tool surface.

The migration path is pinned by `tests/integration/test_migrations.py`: a fresh
sqlite database upgraded to head gains `state_transitions` and `audit_entries`
and stamps the head revision, and a downgrade to base drops them again. The
test drives `scripts/migrate.py` directly, so the wrapper and the baseline are
both covered.

## Consequences

Schema evolution now has one obvious, tested command. Adding a revision is
`scripts/migrate.py revision -m "..."` (with `--autogenerate` to diff the
SQLModel metadata against the database), then `scripts/migrate.py upgrade`; the
deployment guide and an AGENTS.md recipe point at it. No boundary file changes:
`db.py` and the Alembic `env.py` are untouched. The `audit_entries` table stays
reserved (BL-065), so there is no live schema change to migrate yet; this lands
the workflow ahead of the first real evolution, which is the point of BL-051.

## Revisit triggers

Revisit to wire `scripts/migrate.py upgrade` into `deploy/auto-update.sh` ahead
of the service restart: today the auto-update timer fast-forwards and restarts
with no migration step, so a schema-changing release on that path requires
halting the timer and migrating by hand (documented in the deployment guide).
That is acceptable while no migration past the baseline exists, but the first
real revision should land the auto-update integration with it.

Revisit if a deployment needs zero-downtime or multi-step data migrations; the
current model is offline schema migration on a stopped service. Revisit if
`init_db`'s `create_all` and the Alembic head can drift (a model change landing
without a matching revision); a CI check comparing `SQLModel.metadata` against
the head would catch it and is the natural next step. Revisit if a non-sqlite
backend is adopted, which may need dialect-specific migration handling.
