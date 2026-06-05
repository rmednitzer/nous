# Security policy

`nous` is a simulation-based digital twin, not a production C2 system. It
nevertheless ships a deliberate threat model and hardening posture, both
because the project deploys to a public VM and because the twin is meant to
demonstrate audited tool surfaces.

## Reporting a vulnerability

Open a *private* security advisory on GitHub:

    https://github.com/rmednitzer/nous/security/advisories/new

Do not file public issues for security findings. The project commits to:

- **7 days** to acknowledge a report (initial triage, request for
  clarification if needed),
- **14 days** to assessment (impact analysis, fix plan, target release),
- **coordinated disclosure** when a fix lands.

If you need PGP, request the key in the advisory; the maintainer will
publish one on request.

## Scope

In scope:

- The MCP server (`src/nous/server.py`, `src/nous/runner.py`,
  `src/nous/policy.py`, `src/nous/audit.py`).
- The OAuth issuer (`src/nous/auth/`).
- Estimator and interop base classes (`src/nous/estimators/base.py`,
  `src/nous/interop/base.py`) and any concrete adapter that ships.
- The deployment bundle (`deploy/`).

Out of scope:

- Upstream Anthropic API surface. Report security issues with the SDK
  directly to Anthropic.
- Downstream consumers of `nous` outputs (e.g. a TAK server connected to
  the CoT adapter). The adapter is in scope; the downstream is not.

## Hardening posture

### Tier policy gates

Every MCP tool is classified at registration into one of four tiers (T0
read-only, T1 reversible, T2 stateful, T3 irreversible). The runner
refuses any call whose tier the configured policy mode (`open`, `guarded`,
`readonly`) does not admit. The deny list, when set, applies in *every*
mode, including `open`.

### OAuth file-backed lockdown

The OAuth issuer ships in single-client lockdown by default. Tokens and
client registrations live under `$NOUS_HOME/auth/` in JSON files with
mode `0600`. Multi-tenant deployment is out of scope for v0.1; do not
disable single-client lockdown without an ADR.

### Audit log discipline

The audit log is append-only JSONL at `$NOUS_HOME/audit.jsonl`. Output
bodies are SHA-256 hashed and never written. Arguments are passed through
the redaction allowlist before being logged. On Linux, `chattr +a` on the
file gives true append-only semantics; the `logrotate.conf` template in
`deploy/` handles rotation under that constraint.

A daily hash chain over the audit log is *optional* and shipped as a
follow-up (`[BL-031]`); the v0.1 scaffold does not gate behaviour on it.

### SAST suppression catalog

Every inline `# nosec` annotation in `src/nous/` is enumerated in
[`docs/security/bandit-suppressions.md`](docs/security/bandit-suppressions.md)
with its rationale and the test or document that backs the
disposition. The `supply-chain` CI job (`bandit -r src/nous`)
enforces zero unsuppressed findings; a new suppression must land
in the source tree and the catalog in the same PR.

### Secret redaction

`src/nous/audit.py` redacts a fixed set of keys before logging:
`Authorization`, `Cookie`, any key containing `token`, `password`,
`secret`, `api_key`, `bearer`. Argument values that survive redaction are
truncated to a documented length. If you find a redaction gap, report it
as a security advisory.

### No body bytes in audit

The audit record stores `output_sha256` and `output_len` only. The body
is never persisted. Operators who need traceability for a specific
incident pair `output_sha256` with the body the controller saw.

### Audit-degraded posture and kill switches

`device_info` exposes `audit.degraded` and the failure reason. If the
field flips to `true`, the JSONL sink could not be opened or fsynced;
the server falls back to stderr-only logging, which is *not* an
auditable surface. Treat a degraded sink as a hard incident: stop
serving the affected MCP endpoint until the sink is restored. The
2026-05-23 audit (N2) caught this state on the live VM; the runbook
for triage lives in `skills/nous-troubleshooting.md`.

The in-process recovery path is the `audit_resync` MCP tool (T2,
stateful). After an operator remediates the underlying cause
(permissions, mount, `ReadWritePaths=` drift, the audit file moved
out from under the handler), `audit_resync` re-opens the sink in
place; on success `audit.degraded` clears without a service
restart. `fsync_failures` is the cumulative counter and is *not*
reset, so the operator can still see how many writes the degraded
window lost. The `recovered` field in the tool's response
distinguishes "this call cleared a previously-degraded state" from
"the sink was already healthy and the call was a no-op."

The audit handler also runs an opportunistic auto-resync on every
`write()` against a degraded sink: 5-second initial backoff,
doubling up to a 300-second cap on continued failure. The schedule
surfaces through `audit_summary.auto_resync_due_in_s` so an
operator who is actively diagnosing can see when the next retry
will fire. A successful manual `audit_resync` resets the backoff
to its initial value. Auto-resync fires only when a tool call
lands (every audit-write goes through the `write()` path); an
operator who pauses diagnosis by not making tool calls keeps
complete control of the timing.

The live VM auto-update loop (`nous-auto-update.timer`) tracks
`origin/main` every five minutes. Three kill switches and one
rollback path:

```sh
systemctl disable --now nous-auto-update.timer   # stop the auto-update loop
systemctl stop nous.service                      # stop the MCP server itself
echo "$(date -u +%FT%TZ) $(git -C /opt/nous rev-parse origin/main) prev=manual" \
    >> /var/log/nous/auto-update.last_failed    # block the next tick from
                                                 # re-attempting the current
                                                 # origin/main commit
bash /opt/nous/deploy/auto-update-rollback.sh    # roll back to the previous
                                                 # known-good commit
```

The auto-update script records every successful deploy to
`/var/log/nous/auto-update.last_ok` (one line per success, with the
previous-good SHA in a `prev=` field) and every failed
post-restart sanity check to `/var/log/nous/auto-update.last_failed`.
The next tick refuses to redeploy any SHA that appears in
`last_failed`, breaking the every-five-minutes retry loop on a
broken commit. `deploy/auto-update-rollback.sh` reads the most
recent `last_ok` line, resets the working tree to the `prev=` SHA,
re-runs `install.sh`, and restarts `nous.service`; on success it
clears `last_failed` so a corrected `main` can deploy on the next
tick.

The audit log is the authoritative incident artefact; preserve
`/var/log/nous/audit.jsonl` (and any rotated tail) before any
remediation that touches `/opt/nous` or the systemd units. The
auto-update markers under `/var/log/nous/` are the deployment audit
trail; keep them under the same retention as `audit.jsonl`.

## Prompt-injection posture for `inference_cloud`

The `inference_cloud` tool is the seam through which adversarial content
(operator inputs, environmental observations, intercepted comms) can reach
the controller. To bound the blast radius:

- Untrusted content (sensor readings, raw operator transcripts, intercepted
  text) is placed in the *user* message slot of the prompt.
- The system message and tool-result slots are reserved for *trusted*
  content (the controller's own instructions, the self-model's calibrated
  claims, structured engine outputs).
- The Anthropic prompt cache is partitioned so an injection in a cached
  user-slot payload does not pollute the cached system-slot payload.

Treat any change to this partitioning as a security-relevant change.

## Supported versions

Pre-1.0. Only `main` receives security fixes. Tagged releases (`v0.x.y`)
are point-in-time snapshots; if a security fix is needed in a release
branch, the maintainer will cut a new tag from `main` rather than
backporting.

## Acknowledgements

Thanks in advance to the security researchers who take the time to file
reports. Names of acknowledged reporters land in the advisory and the
[CHANGELOG](CHANGELOG.md) once the fix ships.
