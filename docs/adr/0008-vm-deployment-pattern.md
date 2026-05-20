# ADR 0008: VM deployment pattern (Ubuntu 24.04 + systemd + Caddy)

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001, ADR 0005

## Context

The simulator deploys to a single Linux VM. The deployment must:

- start on boot,
- terminate cleanly so per-tick state lands in SQLite,
- expose the MCP HTTP transport behind TLS,
- restrict the OAuth surface to the Anthropic CIDR ranges plus the
  operator's workstation,
- rotate the audit log without re-opening the file descriptor.

## Decision

The deployment bundle in `deploy/` targets Ubuntu 24.04 LTS:

- A `nous.service` systemd unit (`Type=simple`, `ExecStart=` the venv
  Python entry point, `ExecStopPost=` flushes state).
- A daily `nous-state-flush.service` triggered by a
  `nous-state-flush.timer` (`OnCalendar=*-*-* 00:14:00 UTC`,
  `RandomizedDelaySec=15m`, `Persistent=true`).
- A `Caddyfile.example` template: TLS, a CIDR gate on Anthropic's
  published ranges plus the operator's `/32`, and an explicit carveout
  for `/authorize` and `/.well-known/oauth-*` so the OAuth dance works.
- A `logrotate.conf` with `daily`, `rotate 90`, `postrotate chattr +a`
  to keep the audit log append-only after rotation.
- `cloud-init.yaml` installs Python 3.12, git, Caddy, logrotate, and
  sqlite3; creates the `nous` system user; clones the repo; runs
  `install.sh`.
- `install.sh` is idempotent: it creates the venv, installs the
  package, places the systemd units, generates an OAuth signing key if
  one is not present.

## Consequences

Easier: a clean VM goes from cloud-init to a running `nous` in one boot.
The Caddy template makes the OAuth surface auditable.

Harder: the bundle assumes Ubuntu 24.04 LTS and systemd. Other distros
need a port.

## Revisit triggers

- A second OS becomes a deployment target (then split out a `deploy/`
  per OS).
- The OAuth surface needs a public registration endpoint (multi-tenant).
