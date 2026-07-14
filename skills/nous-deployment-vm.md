---
name: nous-deployment-vm
description: Bring up a fresh nous VM using the deploy bundle.
---

# Deployment runbook

Targets Ubuntu 26.04 LTS (ADR 0016); also works on 24.04. The bundle
in `deploy/` is idempotent.

1. Provision a VM with cloud-init enabled. Pass
   `deploy/cloud-init.yaml` as user data.
2. cloud-init installs the platform Python (3.14 on 26.04, 3.12 on
   24.04), git, Caddy, logrotate, sqlite3; creates the `nous`
   system user; clones the repo; runs `deploy/install.sh`.
3. `install.sh` creates the venv (preferring `python3.14`, then
   `python3.13`, then `python3`), installs `nous`, places the systemd
   units, drops a default Caddyfile, and creates the OAuth state
   directory at `$NOUS_HOME/auth/`. The MCP SDK signs OAuth tokens
   internally, so no signing key file is generated.
4. Edit `/etc/caddy/Caddyfile` to set the public hostname and the
   operator CIDR.
5. `systemctl enable --now nous.service nous-state-flush.timer caddy`.
6. Enable auto-update if the deployed host should track `main`:
   `systemctl enable --now nous-auto-update.timer`. The timer polls
   `origin/main` every five minutes, fast-forwards on a change,
   re-runs `install.sh`, and restarts the service. It asserts
   post-restart health (`systemctl is-active`) and exits non-zero on
   failure so the next tick retries. The kill switch is
   `systemctl disable --now nous-auto-update.timer`.

## Verify

- `journalctl -u nous.service -f` follows the server.
- The streamable-HTTP MCP transport is mounted at the root (`/`), not
  `/sse`. `curl -s http://127.0.0.1:8088/.well-known/oauth-authorization-server`
  is the simplest unauthenticated reachability probe (HTTP transport only).
- `tail -f $NOUS_HOME/audit.jsonl` shows audit lines as tools fire.
- `device_info.audit.degraded` must be `false`. If it is `true`, the
  JSONL sink could not be opened; consult `skills/nous-troubleshooting.md`.
- `journalctl -u nous-auto-update.service --since "10 minutes ago"`
  shows the most recent fetch / reset cycle.

## Tear-down

- `systemctl disable --now nous.service caddy nous-state-flush.timer
  nous-auto-update.timer`.
- `rm -rf /opt/nous $NOUS_HOME` (after backing up the state DB and
  audit log).
