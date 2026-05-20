# ADR 0013: Tier-classified subsystem read/write tools

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001, ADR 0007

## Context

Each subsystem exposes both *read* tools (estimator state, observed
sensor values) and a small set of *mutating* tools (inject a fault,
publish a CoT message, force a state transition). Putting every
subsystem tool at the same tier is wrong: the read tools should be
trivially admitted, the mutators should not.

## Decision

For every subsystem, the read tools (`<subsystem>_status`,
`<subsystem>_history`) are classified `T0 READ_ONLY`. Reversible
mutators (`<subsystem>_reset`) are `T1`. Stateful mutators
(`<subsystem>_inject`, `comms_publish`) are `T2`. Irreversible mutators
(`db_reset`, `audit_rotate`) are `T3`.

The classifier table lives in `src/nous/policy.py` and is the single
source of truth.

## Consequences

Easier: a guarded-mode deployment can run read tools freely; a
read-only deployment cannot do anything mutating; the deny list catches
the rest.

Harder: the classifier table grows linearly with the tool surface and
must be maintained alongside `src/nous/server.py`.

## Revisit triggers

- A tool sits awkwardly between tiers; revisit the classification
  table and add a test.
