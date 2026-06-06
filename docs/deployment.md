# Deployment

`nous` deploys to a single Ubuntu 26.04 LTS VM (see ADR 0016). The
bundle in `deploy/` contains everything needed to bring up a fresh
host. The bundle is backwards-compatible with 24.04 LTS, but only the
26.04 path is exercised in production.

## Steps

1. Provision a VM with cloud-init enabled and pass `deploy/cloud-init.yaml`
   as user data. The cloud-init script installs the platform Python
   (3.14 on 26.04, 3.12 on 24.04), git, Caddy, logrotate, and sqlite3;
   creates the `nous` system user; clones this repository; and runs
   `deploy/install.sh`.
2. `install.sh` is idempotent. It creates the venv at
   `/opt/nous/venv` (preferring `python3.14` -> `python3.13` ->
   `python3`), runs `pip install .`, places the systemd units
   (`nous.service`, `nous-state-flush.{service,timer}`,
   `nous-auto-update.{service,timer}`) in `/etc/systemd/system/`,
   drops a default `/etc/caddy/Caddyfile` based on
   `deploy/Caddyfile.example`, and creates the OAuth state directory
   at `$NOUS_HOME/auth/` (the MCP SDK signs tokens internally; no
   signing key file is generated).
3. Edit `/etc/caddy/Caddyfile` to set the public hostname and the
   operator CIDR.
4. `systemctl enable --now nous.service nous-state-flush.timer caddy`.
5. To track `main` automatically:
   `systemctl enable --now nous-auto-update.timer`. The timer polls
   `origin/main` every five minutes, fast-forwards on a change,
   re-runs `install.sh`, and restarts `nous.service` (asserting
   post-restart `systemctl is-active`). Kill switch:
   `systemctl disable --now nous-auto-update.timer`.
6. Verify: `device_info` should report `audit.degraded: false`. A
   `true` here means the JSONL sink could not be opened; consult
   `skills/nous-troubleshooting.md` before serving traffic.

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

## Observability

The tick loop is instrumented with OpenTelemetry metrics (BL-037, ADR 0036):
a `nous.tick.duration` histogram and a `nous.tick.overruns` counter. `nous`
depends only on the OTel API, so the instruments are no-ops until a provider
is configured: by default the per-tick `record` call does no SDK, exporter, or
collector work, and there is nothing to scrape.

To export them, install the SDK plus an exporter and launch the server under
the OTel auto-instrumentation wrapper, which reads the standard `OTEL_*`
environment variables (no `nous`-specific configuration is needed):

```sh
pip install opentelemetry-sdk opentelemetry-exporter-otlp opentelemetry-distro
OTEL_SERVICE_NAME=nous \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317 \
  opentelemetry-instrument python -m nous serve
```

## Upgrades

Pull, `pip install -U .`, `systemctl daemon-reload && systemctl restart
nous.service`. The state DB carries over; the audit log is append-only and
unaffected.

If a release ships a schema change, apply it offline before the new code
restarts (Alembic under the hood). Stop the service first so it releases its
open handle on the sqlite database: the migration model is offline on a
stopped service (ADR 0037), and migrating underneath the live process can race
with its writes. Run the migration as the `nous` service account through the
deployed venv (`/opt/nous/venv`, where `install.sh` installs the project and
Alembic), with the service environment loaded. Running as `nous` keeps a
freshly created `state.db` and its `-wal`/`-shm` sidecars owned by the service
rather than the operator; loading `/etc/nous/nous.env` (which the unit reads as
its `EnvironmentFile`) keeps `resolved_db_url()` on the same database the unit
uses instead of the local default:

```sh
sudo systemctl stop nous.service
sudo -u nous bash -c '
  set -a; . /etc/nous/nous.env; set +a
  /opt/nous/venv/bin/python /opt/nous/scripts/migrate.py current   # what the DB is on now
  /opt/nous/venv/bin/python /opt/nous/scripts/migrate.py upgrade   # to head
'
sudo systemctl start nous.service
```

A schema-changing release needs this before the new code runs, but the
auto-update timer (below) fast-forwards and restarts on its own with no
migration step. For such a release, halt the timer first (see "Halt the
auto-deploy loop"), migrate manually, then restart and re-enable. Wiring the
runner into `deploy/auto-update.sh` ahead of the restart is the eventual fix
(an ADR 0037 revisit trigger); until then this stays a manual, timer-halted
step.

See [ADR 0037](adr/0037-schema-migration-workflow.md) for the workflow and
`scripts/migrate.py --help` for the full subcommand set.

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
