# ADR 0007: Additive-surface rule beyond L0

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001

## Context

Once the v0.1 scaffold is in, the MCP tool surface, the hardware-profile
schema, the database tables, and the audited-runner signature become
external contracts. Changing any of them silently breaks downstream
consumers (scenarios, deployed `nous` instances on shared VMs,
controllers that have memorised tool signatures).

## Decision

From L1 onward (i.e. once v0.1 ships), all surface changes must be
*additive* unless an ADR explicitly authorises a breaking change:

- MCP tools may gain new optional parameters with defaults that preserve
  the prior behaviour. New tools land beside the old ones.
- Profile YAML may gain new optional fields. New required fields require
  a profile migration plus an ADR.
- Database tables may gain new optional columns. Schema migrations live
  in `alembic/versions/`.
- The runner signature (`nous.runner.run`) and audit record schema
  (`AuditRecord`) are stable. Adding a field is additive; removing or
  renaming one needs an ADR.

The CI grep checks the changelog for `feat!:` / `BREAKING CHANGE` lines
and refuses to land them without a paired ADR file.

## Consequences

Easier: downstream consumers can pin against a `nous` version without
fear of a quiet rename. The release notes are honest.

Harder: the maintainer must say no to a tempting rename. Some
contributors will find the discipline tedious.

## Revisit triggers

- A v1.0 release tightens the contract; we may further restrict what
  counts as additive.
- A security-relevant rename becomes necessary; the ADR covers it.
