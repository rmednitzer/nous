---
name: nous-troubleshooting
description: Common failure patterns and how to read the audit log.
---

# Troubleshooting

## A tool returns "[DENIED ...]"

The policy mode refused the tier. `device_info` reports the active
mode (`open`, `guarded`, `readonly`). Either re-issue against a lower-
tier read tool or have the operator lower the policy mode.

## A tool returns "[error ...]"

The runner caught an exception. The audit record is still written;
the next-best signal is the prefix (`error <class>`). Check the
underlying subsystem with its `*_status` read.

## The Anthropic daily cap is exhausted

`anthropic_cap_status` reports `exhausted: true` (and `remaining: 0`) once
the daily cap is reached; the cloud path then fails closed with
`CapExhausted`. Fall back to `inference_local`. The cap rolls over at UTC
midnight. (The `inference_cloud` tool that consumes the cap is classified
in `policy.py` but not yet registered; `anthropic_cap_status` is the signal
to branch on today.)

## The audit log looks empty

Confirm `device_info.audit.path` is writable. On Linux, `chattr +a` on
the file blocks naive writers; the WatchedFileHandler is happy with
append-only.

## `device_info` reports `audit.degraded: true`

The JSONL sink could not be opened or fsynced. The server is falling
back to stderr-only logging; that is **not** an auditable surface.
Treat this as an incident, not a warning. Triage:

1. SSH to the host. Confirm `device_info.audit.path` (default
   `/var/log/nous/audit.jsonl`) exists and is owned by the running
   user. The install bundle creates `/var/log/nous/` owned by the
   `nous` user.
2. Check the systemd unit's `ReadWritePaths=` matches the audit path;
   `ProtectSystem=strict` plus a stale `ReadWritePaths` denies the
   write.
3. Tail `journalctl -u nous.service` for the failure reason; the
   audit handler writes `audit fsync failed: ...` to stderr on each
   failed flush.
4. After the underlying cause is fixed, call the `audit_resync`
   MCP tool (T2). The handler re-opens in place; on success
   `device_info.audit.degraded` flips back to `false` without a
   service restart. `fsync_failures` is cumulative so an operator
   can still see how many writes the degraded window lost. If the
   call returns `degraded: true` and `recovered: false`, the
   underlying cause is still present; re-check steps 1 through 3.
5. If you wait, the handler will retry on its own. The
   opportunistic auto-resync runs on every `write()` against a
   degraded sink with a 5-second initial backoff that doubles up
   to a 300-second cap. `audit_summary.auto_resync_due_in_s`
   shows the time until the next attempt. Auto-resync fires only
   when a tool call lands (every audit-write goes through the
   `write()` path); pausing tool calls keeps the timing under
   your control. A successful manual `audit_resync` resets the
   backoff to its initial value.
6. As a last resort, stop the service (`systemctl stop nous.service`)
   until the sink is restored. The 2026-05-23 audit (N2) caught the
   live VM in this state; the `audit_resync` tool and the auto-
   resync schedule (closes N2) are the in-process recovery paths
   that replace the restart.

## Confirming the audit trail has not been tampered with

Two T0 reads check audit integrity, and they answer different questions:

1. `audit_verify` walks the on-disk hash chain (ADR 0025 / BL-016). `ok:
   false` means a record was mutated, deleted mid-stream, inserted, or
   reordered, and `first_break_line` is where. `from_genesis: false` on an
   otherwise-`ok` log is a normal post-rotation continuation segment, not
   tampering.
2. `audit_anchor_verify` cross-checks the daily anchors (ADR 0026 / BL-031)
   against the chain. The hash chain alone cannot see tail truncation
   (dropping the most recent records leaves a shorter, still-consistent
   chain); the anchor pins the chain head once per UTC day in
   `device_info.audit.anchor_path`, so an anchored head that has gone
   missing means the tail was cut. `ok: false` with a `truncation` reason
   and a `first_break.day` is that signal. `unverifiable` counts anchors
   whose content has aged out of the retained logrotate segments (not a
   break). Run this after any suspected `chattr -a` window.

Neither read is access control: both supplement the append-only bit and
off-host shipping. A clean pair is evidence, not proof, that the medium
was never writable.

## The live VM is serving an older tool surface

The auto-update timer tracks `origin/main` every five minutes. If
`origin/main` lags the development line, the live MCP serves the
older surface even though the development line registers more
tools. Triage:

1. `journalctl -u nous-auto-update.service --since "10 minutes ago"`
   shows the most recent fetch / reset / restart cycle.
2. Confirm the merge to `main` has actually landed
   (`git ls-remote origin main`); a development branch that consumed
   merge commits locally without pushing them does not move the live
   VM.
3. To suspend auto-update during incident triage:
   `systemctl disable --now nous-auto-update.timer`. Re-enable when
   the merge lands.

## The FSM refuses a transition

`state_history` shows what was attempted. The transition table in
`src/nous/state/machine.py` is the authoritative reference. ADR 0018
documents the safety guards: SC-2 thermal headroom (`IDLE -> MISSION`
and similar) and the low-power blocker (`LOW_POWER -> recover`).
