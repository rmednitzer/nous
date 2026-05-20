# Deployment bundle

Files in this directory bring up a `nous` instance on a fresh Ubuntu
24.04 LTS VM. See [`docs/deployment.md`](../docs/deployment.md) for
the full walkthrough.

| File | Purpose |
|------|---------|
| `cloud-init.yaml` | Cloud-init user data. |
| `install.sh` | Idempotent installer (venv, systemd, Caddy, OAuth key). |
| `systemd/nous.service` | Main process unit. |
| `systemd/nous-state-flush.service` | Daily state flush. |
| `systemd/nous-state-flush.timer` | Daily timer (00:14 UTC). |
| `Caddyfile.example` | Caddy template (TLS, CIDR gate, OAuth carveout). |
| `logrotate.conf` | Daily rotation with `chattr +a` on rotate. |
