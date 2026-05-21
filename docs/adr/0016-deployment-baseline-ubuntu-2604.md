# ADR 0016: Deployment baseline upgrades to Ubuntu 26.04 LTS

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0008
- **Supersedes:** ADR 0008

## Context

ADR 0008 set the VM deployment baseline to Ubuntu 24.04 LTS. Canonical
shipped Ubuntu 26.04 LTS in April 2026, and the live reference instance
now tracks it (commit `d9d3f6e` already adjusted the cloud-init
package names to make the bundle land on the new image). This ADR
records the deployment baseline now formally moving to 26.04 and
captures the systemd hardening that the newer release lets us pin.

Three things changed under the bundle that motivated the migration.
The platform Python is now 3.14, which the simulator already runs
clean under and which delivers measurable speedups on the tick loop
via the tail-calling interpreter and free-threaded build (PEP 779,
no longer experimental). The shipped systemd is recent enough to
expose `ProtectProc`, `ProtectClock`, `ProtectHostname`, and
`ProcSubset` unconditionally; the previous unit could not rely on
these directives being implemented on every supported host. The
LTS support window now extends to April 2031 (standard) with ESM
through 2036, which pushes the next forced OS migration past the
v1.0 roadmap.

## Decision

The `deploy/` bundle now targets Ubuntu 26.04 LTS. The specific
changes that landed alongside this ADR:

- `cloud-init.yaml` keeps `python3` / `python3-venv` as the
  version-agnostic meta-packages (so the install still works on
  24.04 too) and the header comment names 26.04 as the baseline.
- `install.sh` prefers `python3.14`, then `python3.13`, then plain
  `python3`. On 26.04 the first branch hits, on 24.04 the
  fallback resolves to 3.12, and a contributor running a custom
  build (uv-managed 3.13) gets the middle branch.
- `systemd/nous.service` adds the hardening directives that the
  26.04 systemd implements: `ProtectClock=true`,
  `ProtectHostname=true`, `ProtectProc=invisible`,
  `ProcSubset=pid`, `RestrictNamespaces=true`,
  `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`,
  `MemoryDenyWriteExecute=true`, `RemoveIPC=true`,
  `KeyringMode=private`, `UMask=0077`, `CapabilityBoundingSet=`
  (empty), `AmbientCapabilities=` (empty), and a
  `SystemCallFilter=@system-service` allowlist with the
  privileged groups (`@privileged @resources @debug @mount
  @cpu-emulation @obsolete @raw-io @reboot @swap`) explicitly
  denied. The same edit also extends `ReadWritePaths=` to
  `/var/log/nous` so the audit log path the cloud-init env file
  points at (`NOUS_AUDIT_PATH=/var/log/nous/audit.jsonl`) is
  writable under `ProtectSystem=strict`; the previous unit only
  named `/var/lib/nous`, which meant the audit sink fell back to
  its degraded path on a strict-mode read-only filesystem.
- `pyproject.toml` keeps `requires-python = ">=3.12"` so a
  contributor on a 24.04 box can still `uv sync`. The classifier
  list grows `Python :: 3.13` and `Python :: 3.14` entries to
  signal the deployment target.

Documentation throughout the tree (README, deployment guide,
deployment skill, deploy README, AGENTS) names Ubuntu 26.04 LTS
and Python 3.14 as the deployment baseline.

## Consequences

Easier: the new hardening directives cover clock tampering,
hostname spoofing, and `/proc` exposure that the previous unit
could not block portably. The longer LTS window pushes the next
forced OS migration past 2030. Python 3.14 lands the tail-calling
interpreter and the free-threaded build as Tier 1 features; even
without the GIL-off mode the inner tick loop is measurably faster
than on 3.12. The strict `RestrictAddressFamilies` list (UNIX,
IPv4, IPv6) blocks AF_PACKET, AF_NETLINK, AF_BLUETOOTH and the
long tail of socket families the server never uses. The
`ReadWritePaths` fix means the audit log lands at the spec path
without falling back to stderr.

Harder: a 24.04 host can still run the bundle (`install.sh` falls
back, unknown systemd directives are ignored with a warning), but
CI does not exercise that path. A regression in the 24.04
fallback would land silently. Operators on 24.04 should pin a
`systemctl edit nous.service` override if they want to retain the
older unit shape; the auto-updater re-installs the new unit on
every `origin/main` advance.

Alternatives rejected:

- Keep 24.04 as the only supported baseline. The LTS window is
  the decisive lever: April 2029 (standard) vs April 2031.
- Support both 24.04 and 26.04 as first-class targets, with a
  matrix in CI. Doubles the test surface for a deployment style
  only one operator currently runs.

## Revisit triggers

- Ubuntu 28.04 LTS lands (April 2028 by Canonical's cadence).
- A profile or scenario legitimately needs a capability the new
  systemd sandbox blocks (e.g., a packet-capture sensor would
  need AF_PACKET back).
- The free-threaded 3.14t interpreter becomes the archive
  default and the engine can be retuned to use per-tick
  parallelism.
