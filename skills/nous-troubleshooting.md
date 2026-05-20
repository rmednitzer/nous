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

## `inference_cloud` returns `CapExhausted`

The Anthropic daily cap is exhausted. Fall back to `inference_local`.
The cap rolls over at UTC midnight.

## The audit log looks empty

Confirm `device_info.audit.path` is writable. On Linux, `chattr +a` on
the file blocks naive writers; the WatchedFileHandler is happy with
append-only.

## The FSM refuses a transition

`state_history` shows what was attempted. The transition table in
`src/nous/state/machine.py` is the authoritative reference.
