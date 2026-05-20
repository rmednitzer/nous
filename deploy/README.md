# Deployment bundle

Files in this directory bring up a `nous` instance on a fresh Ubuntu
26.04 LTS VM (ADR 0016). The same bundle also runs on 24.04 LTS: the
installer walks `python3.14` -> `python3.13` -> `python3` and
selects the first interpreter present, and the systemd unit's newer
hardening directives are ignored with a warning by older systemd.
See [`docs/deployment.md`](../docs/deployment.md) for the full
walkthrough.

| File | Purpose |
|------|---------|
| `cloud-init.yaml` | Cloud-init user data. |
| `install.sh` | Idempotent installer (venv, systemd, Caddy, OAuth key). |
| `systemd/nous.service` | Main process unit. |
| `systemd/nous-state-flush.service` | Daily state flush. |
| `systemd/nous-state-flush.timer` | Daily timer (00:14 UTC). |
| `Caddyfile.example` | Caddy template (TLS, CIDR gate, OAuth carveout). |
| `logrotate.conf` | Daily rotation with `chattr +a` on rotate. |
