# ADR 0025: Tamper-evident audit hash chain

- **Status:** Accepted
- **Date:** 2026-06-01
- **Authors:** rmednitzer
- **Builds on:** ADR 0002, ADR 0007, ADR 0012

## Context

The audit log is the project's primary off-host evidence. `audit.py`
already writes one append-only JSONL line per tool call, records the
output as a SHA-256 plus a byte length (never the body), fsyncs every
record to stable storage, and shapes each line for EU AI Act Art. 12
(automatic recording) and CRA Art. 13 (security logging). The handler
is rotation-safe and the deployment makes the file append-only with
`chattr +a`.

What the log does not have is an integrity link between records. Each
line stands alone, so a process (a bug, or an attacker with write
access during a window when the append-only bit is off) can edit a
field in a past line, drop a line from the middle, or reorder the
file, and nothing in the artefact records that it happened. The
`output_sha256` proves the body matches its hash for that one line; it
says nothing about whether the line belongs where it sits, or whether
a sibling line was removed. A conformity-assessment body replaying the
trail (the stated purpose of the schema in `AuditRecord`) cannot today
tell an intact log from a selectively edited one.

BL-016 names this gap and asks for a hash chain. The shape that closes
it is the standard one: each record commits to the hash of the record
before it, so the most recent hash is a fingerprint of the entire
history. Any in-place edit or mid-stream deletion breaks the link at
the point of tampering and every link after it, which a verifier can
locate. The chain has to be additive (ADR 0007): existing readers must
keep working, and lines written before the upgrade must remain valid
records, just unchained.

## Decision

`AuditRecord` gains two optional string fields, `prev_hash` and
`entry_hash`, both defaulting to empty so every existing constructor
and every existing line stays valid. `entry_hash` is the SHA-256 of
the canonical JSON of the record with `entry_hash` excluded and
`prev_hash` included, where canonical means sorted keys and tight
separators so a verifier reconstructs the same bytes regardless of
field-definition order. Because `prev_hash` is part of the hashed
content, each `entry_hash` commits to its predecessor, and the chain
is the sequence of those commitments.

`AuditLogger` owns the chain head. The genesis value is sixty-four
zeros, a value no real SHA-256 of a record produces, so the first
chained line is unambiguous. At construction the logger recovers the
head from the tail of the existing file (the last line's `entry_hash`,
or genesis if the file is empty or its last line predates the chain),
so the chain survives a process restart and spans a log rotation as
long as the process keeps running. `write()` stamps `prev_hash` from
the head, computes `entry_hash`, emits the line, and advances the head
only when the emit did not raise. The per-record cost is one SHA-256
over a short canonical string, negligible beside the output hash and
the fsync the handler already pays.

A module-level `verify_chain(path)` walks a JSONL file and returns a
structured result: whether the chain is intact, how many lines were
checked, how many were chained versus legacy, and the line number and
reason of the first break. Lines without an `entry_hash` are treated
as a legacy prefix and skipped, so a file that straddles the upgrade
verifies cleanly from its first chained record. A new T0 `audit_verify`
MCP tool exposes the walk to a controller, and `summary()` (hence
`audit_summary`) surfaces the current `chain_head` so a controller can
read the fingerprint without scanning the file.

The decision is deliberately scoped to in-band tamper-evidence for a
single-writer append-only log. It does not sign the chain and does not
anchor it off-host, so it raises the cost of selective tampering and
makes mutation and mid-stream deletion detectable; it does not by
itself stop an attacker who can rewrite the whole file from recomputing
a fresh consistent chain. The external defences (the append-only bit,
shipping the log off-host, and the daily anchor in BL-031) are
complementary and stay where they are.

## Consequences

Easier: the integrity of the audit trail becomes a mechanical check
rather than a matter of trust. A controller asks `audit_verify` and
gets a yes or no with the first broken line if the answer is no; a
conformity-assessment body replays the file with the same function. A
mutated or mid-stream-deleted record surfaces at the exact line, with
every downstream link flagged, instead of hiding in a plausible-looking
log. The chain head in `audit_summary` is a single value a controller
can pin and compare across reads.

Harder: `audit.py` (a boundary surface under CLAUDE.md and AGENTS.md)
grows chain state, a recovery read at construction, and the verifier,
so this ADR is the required record for the change. The audit-line
schema gains two fields, versioned per ADR 0012; downstream consumers
that pinned the old field set should widen their parser. The chain is
single-writer by construction: two processes writing the same file
would interleave and break it, which is already outside the deployment
model (one `nous.service`, one audit file) but is now load-bearing.

Two limits are explicit so no one over-reads the property. The chain
detects mutation and mid-stream deletion, insertion, or reordering; it
does not detect tail truncation, because removing the most recent N
lines leaves a shorter but internally consistent chain. Closing that
needs an external anchor (a periodically recorded head, the BL-031
daily anchor), which is tracked separately. And the chain is evidence,
not access control: it is only as strong as the medium it sits on, so
it supplements `chattr +a` and off-host shipping rather than replacing
them.

Alternatives rejected:

- **Per-file Merkle tree.** Stronger membership proofs, but the audit
  log is append-only and single-writer, so a linear chain gives the
  same tamper-evidence with no tree to rebuild on every append.
- **Sign each line.** Tamper-evidence plus authenticity, but it pulls
  in key management and rotation, which belongs with the regulated-
  deployment hardening in BL-059, not the base chain.
- **External WORM medium only.** Orthogonal and still wanted, but it
  protects the file, not the record relationships; an in-band chain
  makes a copied-off log self-verifying without the original medium.

## Revisit triggers

- BL-031 lands a daily anchor (a recorded or signed chain head per
  UTC day). The anchor closes the tail-truncation gap and this ADR's
  "does not detect truncation" limit should be narrowed to "between
  anchors."
- The audit log ever becomes multi-writer (multi-tenant L3, BL-045).
  A linear single-writer chain no longer holds and the design needs a
  per-writer chain or a serializing sink.
- A regulator asks for signed audit evidence. The chain should grow a
  signature over the head rather than over each line, aligned to
  whatever format the body accepts.
- The recovery read at construction shows up as a startup cost on a
  very large log. A bounded tail read (seek to the end, scan back to
  the last newline) replaces the full-file read if needed.
