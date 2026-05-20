# Deployment

`nous` deploys to a single Ubuntu 24.04 LTS VM. The bundle in `deploy/`
contains everything needed to bring up a fresh host.

## Steps

1. Provision a VM with cloud-init enabled and pass `deploy/cloud-init.yaml`
   as user data. The cloud-init script installs Python 3.12, git,
   Caddy, logrotate, and sqlite3; creates the `nous` system user;
   clones this repository; and runs `deploy/install.sh`.
2. `install.sh` is idempotent. It creates the venv at
   `/opt/nous/venv`, runs `pip install .`, places the systemd units
   (`nous.service`, `nous-state-flush.{service,timer}`) in
   `/etc/systemd/system/`, drops a default `/etc/caddy/Caddyfile`
   based on `deploy/Caddyfile.example`, and generates an OAuth signing
   key under `$NOUS_HOME/auth/` if one is not present.
3. Edit `/etc/caddy/Caddyfile` to set the public hostname and the
   operator CIDR.
4. `systemctl enable --now nous.service nous-state-flush.timer caddy`.

## Configuration

Every knob is an `NOUS_*` environment variable read by
`pydantic-settings`. The systemd unit reads `/etc/nous/nous.env`.
Common settings:

| Variable | Default | Notes |
|----------|---------|-------|
| `NOUS_HOME` | `/var/lib/nous` | State, audit, OAuth data. |
| `NOUS_TRANSPORT` | `stdio` | `http` for the Caddy-fronted deployment. |
| `NOUS_HTTP_BIND` | `127.0.0.1:8088` | Bound behind Caddy. |
| `NOUS_POLICY` | `open` | `guarded` / `readonly` to tighten. |
| `NOUS_PROFILE` | `jetson-agx-orin` | Profile YAML name. |
| `NOUS_TICK_HZ` | `2.0` | Tick cadence. |
| `NOUS_ANTHROPIC_API_KEY` | (unset) | Cloud inference. |
| `NOUS_ANTHROPIC_DAILY_CAP` | `100` | Hard cap per UTC day. |
| `NOUS_OAUTH_ENABLED` | `false` | Required for HTTP transport. |
| `NOUS_OAUTH_SINGLE_CLIENT` | `true` | Lockdown (do not disable without an ADR). |

## Logs

The audit log lives at `$NOUS_HOME/audit.jsonl`. The bundled
`deploy/logrotate.conf` rotates daily and keeps 90 days. `postrotate`
runs `chattr +a` to restore append-only semantics on Linux.

The systemd journal carries the rest of the process output. `journalctl
-u nous.service -f` follows it.

## Upgrades

Pull, `pip install -U .`, `systemctl daemon-reload && systemctl restart
nous.service`. The state DB carries over (Alembic handles migrations);
the audit log is append-only and unaffected.

## Auto-deploy from `main`

The live VM tracks `origin/main`. A oneshot systemd unit
(`nous-auto-update.service`) runs `deploy/auto-update.sh`, which:

1. `git fetch origin main`
2. If `HEAD == origin/main`, exits 0 (silent no-op).
3. Otherwise: `git reset --hard origin/main`, `bash deploy/install.sh`,
   `systemctl daemon-reload`, `systemctl restart nous.service`,
   asserts the service came back active.

The companion timer (`nous-auto-update.timer`) fires every 5 minutes
after a 2-minute post-boot delay, with up to 30 s of randomised
jitter. A log line lands in `/var/log/nous/auto-update.log` on every
successful update; silent ticks emit no log entry.

### Halt the auto-deploy loop

If a bad merge needs to be paused before the next tick:

```bash
sudo systemctl disable --now nous-auto-update.timer
```

Resume with `enable --now`. The timer is enabled by default in
the cloud-init bootstrap.

### Trigger a one-off update manually

```bash
sudo systemctl start nous-auto-update.service
journalctl -u nous-auto-update.service -n 30 --no-pager
```

### Why polling instead of a webhook?

No GitHub-side secrets, no public webhook endpoint to defend, no
GitHub Actions runner permissions to manage. The 5-minute deploy
latency is acceptable for a single-VM service; switch to a webhook
or a workflow-dispatched deploy if/when that changes.
