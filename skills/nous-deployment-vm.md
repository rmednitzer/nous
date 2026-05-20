---
name: nous-deployment-vm
description: Bring up a fresh nous VM using the deploy bundle.
---

# Deployment runbook

Targets Ubuntu 24.04 LTS. The bundle in `deploy/` is idempotent.

1. Provision a VM with cloud-init enabled. Pass
   `deploy/cloud-init.yaml` as user data.
2. cloud-init installs Python 3.12, git, Caddy, logrotate, sqlite3;
   creates the `nous` system user; clones the repo; runs
   `deploy/install.sh`.
3. `install.sh` creates the venv, installs `nous`, places the systemd
   units, drops a default Caddyfile, and generates an OAuth signing
   key if missing.
4. Edit `/etc/caddy/Caddyfile` to set the public hostname and the
   operator CIDR.
5. `systemctl enable --now nous.service nous-state-flush.timer caddy`.

## Verify

- `journalctl -u nous.service -f` follows the server.
- `curl -s http://127.0.0.1:8088/sse` should return a streamable
  response (HTTP transport only).
- `tail -f $NOUS_HOME/audit.jsonl` shows audit lines as tools fire.

## Tear-down

- `systemctl disable --now nous.service caddy nous-state-flush.timer`.
- `rm -rf /opt/nous $NOUS_HOME` (after backing up the state DB and
  audit log).
