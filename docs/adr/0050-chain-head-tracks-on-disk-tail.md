# ADR 0050: The audit chain head tracks the on-disk tail, not the fsync confirmation

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer
- **Builds on:** ADR 0025, ADR 0001

## Context

`AuditLogger.write` (`audit.py`) stamps each record with the hash chain (ADR
0025 / BL-016), emits it, advances the in-memory `_chain_head` to the new
record's `entry_hash`, and then polls `_sync_fsync_failure_state` for a silent
fsync failure on the handler. The 2026-06-14 audit (AUD-1) flagged the ordering:
the head advances before durability is confirmed, so on a silent fsync failure
the head briefly references a record that reached the page cache but may not be
on stable storage. The finding proposed a remediation: move the head advance
inside the clean-fsync branch so only a durably written record advances it.

On inspection that remediation is unsafe, because it conflates two different
heads. `_FsyncingFileHandler.emit` writes and flushes the line into the file
*before* it calls `os.fsync`, and a failed fsync is caught rather than raised,
so an fsync-failed record is already physically present in the append-only log.
The chain is a tamper-evidence structure over what is on disk: `verify_chain`
walks the file and requires each record's `prev_hash` to equal its physical
predecessor's `entry_hash`. If the head did not advance past an fsync-failed
record, the next record would link to the prior line instead, skipping a line
that is physically there, and `verify_chain` would break at it. The proposed fix
would turn a narrow, already-signalled durability window into real on-disk chain
corruption.

The exposure the finding names is in practice nil. The in-memory head is
discarded on a crash and rebuilt from the file tail by `_recover_chain_head` on
the next open, so a head that referenced a not-yet-durable record has no
successor consequence: either the page cache reached disk (the tail has the
record, the head is correct) or it did not (the tail ends at the prior record,
the head recovers there, the chain is still consistent). Durability is a
separate concern from linkage, and it is already tracked separately.

## Decision

Keep the head advancing for every emitted record, and write the invariant down
so no future change re-introduces the bug: `_chain_head` tracks the on-disk
tail, not the fsync confirmation. The log is append-only (`O_APPEND` plus
`chattr +a`) and the handler writes before it fsyncs, so every emitted record is
part of the physical tail and the next record must link to it.

Reorder `write` so the `_sync_fsync_failure_state` poll runs before the
head advance, with the head advance left unconditional and the invariant stated
in a comment at the point a contributor would otherwise reach for a `if
durable:` guard. The reorder is behaviour preserving: the head still advances on
every emit that does not raise, and only `writes_total` and `last_write_ts_s`
stay gated on a clean fsync. Durability remains observable through `degraded`,
`fsync_failures`, the fsync-gated `writes_total`, the opportunistic auto-resync,
and the BL-031 daily anchor that closes tail truncation.

## Consequences

The audit chain stays verifiable across a silent fsync failure, and that
property is now pinned by a regression test: a write whose fsync fails is still
linked by the next write, and the file verifies clean. A contributor who later
tries to "tighten" `write` by gating the head advance on a clean fsync fails
that test, which is the guard the documentation cannot enforce on its own.

There is no behaviour change. AUD-1 closes as remediated by documentation plus a
regression guard rather than by a code path change, because the code path was
already correct and the proposed change was the hazard. The audit log keeps its
single contract: the head a verifier reconstructs from the file always matches
the head the writer advanced.

Alternatives rejected. Gating the head advance on a clean fsync corrupts the
chain, as above. Making the log rewritable so an unconfirmed record could be
replaced defeats the append-only tamper-evidence the whole structure rests on
(ADR 0025) and the `chattr +a` deployment posture. Fsyncing before the emit is
not possible: there is no line to fsync until it has been written.

## Revisit triggers

- The handler is changed to fsync before it writes the line into the file, at
  which point a record could be both unwritten and unconfirmed together, and
  gating the head advance on durability would become both safe and meaningful.
- The durability model moves to a write-ahead or double-write scheme where the
  physical tail and the confirmed tail are deliberately distinct structures.
