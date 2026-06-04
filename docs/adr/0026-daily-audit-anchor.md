# ADR 0026: Daily audit anchor

- **Status:** Accepted
- **Date:** 2026-06-04
- **Authors:** rmednitzer
- **Builds on:** ADR 0002, ADR 0007, ADR 0025

## Context

ADR 0025 gave the audit log a per-record hash chain: each line commits to
its predecessor, so any in-place mutation or mid-stream deletion, insertion,
or reordering breaks a link that `verify_chain` locates. That ADR was also
explicit about the one thing the chain cannot do. Dropping the most recent
records leaves a shorter chain that is still internally consistent, so
`verify_chain` still passes. LIMITATIONS L18 records the same gap, and both
ADR 0025 and ADR 0002 name BL-031 as the follow-up that closes it.

Tail truncation is the realistic attack on a seized or compromised box: cut
the last N lines to erase the evidence of the most recent actions. The chain
head is a fingerprint of the entire history, but nothing outside the file
remembers what that fingerprint was a day ago, so a verifier reading only
the current file has no reference point to notice that the tail is missing.

What is needed is a second, independently retained record of the chain head,
taken on a cadence and kept where truncating the main log does not also
truncate it. That record does not need to sign anything (signing belongs to
the regulated-deployment track, BL-059); it needs to exist separately and be
itself tamper-evident.

## Decision

A new module, `src/nous/audit_anchor.py`, records the audit chain head at
most once per UTC day into a separate append-only file
(`$NOUS_HOME/audit-anchors.jsonl` by default, beside the audit log).
`AnchorLog.maybe_anchor` is driven from the server's audited-runner wrapper
(`server.py::_wrap`), which is the right cadence because the audit chain only
advances on a tool call. The common path is a single date comparison; on the
first call of a new UTC day it reconstructs the chain, captures the head and
the chained-record count, and appends one `AnchorRecord`. The anchor file is
itself a hash chain (`prev_anchor_hash` / `anchor_hash`, using the same
canonical SHA-256 as the audit chain), so the anchors cannot be edited
undetected either.

`verify_anchors(audit_path, anchor_path)` cross-checks the two artefacts and
a new T0 `audit_anchor_verify` tool exposes it. Each anchored head commits to
its whole prefix, so a head that is present and linked proves that prefix is
intact, and a head that is absent means the chain was cut at or before it.
The newest anchor must always be present: it pins the most recent UTC day
with audit activity, which lives in the active (or near-active) segment and
is therefore within retention, so its absence is the truncation signal (the
realistic attack is wiping the active log, after which new records link to a
stale in-memory head and contain none of the anchored heads). Among the older
anchors, retention drops the oldest content first, so a contiguous absent
prefix is the legitimate "rotated out of the window" case (reported
`unverifiable`); an anchor absent after a present one means newer content was
removed out of order, which is a break.

The verifier reconstructs across the conventional logrotate siblings
(`audit.jsonl`, `audit.jsonl.1`, `audit.jsonl.2.gz` and upward, gunzipping
transparently) oldest first, recomputing every `entry_hash` and checking
`prev_hash` linkage within each segment. At a segment boundary the first
record must root at genesis (a logrotate followed by a restart leaves the
recovered head at genesis, so the new active file is a fresh genesis-rooted
segment) or continue from the previous segment's head; a link to anything
else is a dangling reference left by a deletion at the boundary, and a
non-genesis link after a legacy (pre-chain) prefix is the same deletion at
the upgrade boundary that `verify_chain` rejects. The oldest retained segment
has no earlier reference, so its first record only sets `from_genesis`. The
anchor cross-check then tests membership against the union of all segment
heads. A segment that is unreadable, a corrupt `.gz` payload, or an
unlistable audit directory is reported as a structured `audit_chain_ok:
false`, never allowed to escape as an exception. `policy.py`
classifies `audit_anchor_verify` as T0 (this ADR is the required record for
that boundary edit), `install.sh` creates the anchor file and makes it
append-only with `chattr +a` the way it already does for the audit log, and
the anchor file is deliberately not rotated: its whole value is long-term
retention of one short line per day.

## Consequences

Easier: tail truncation becomes a mechanical check. A controller (or a
conformity-assessment body replaying the trail) asks `audit_anchor_verify`
and learns whether every anchored head is still present, with the offending
day named when one is missing. The anchor file is a second small artefact a
deployment ships off-host, so erasing recent evidence now means tampering
with two files consistently rather than one. The cost is one extra full-file
read and a one-line fsync per UTC day, on a tool call, which is negligible
beside the per-call audit fsync.

Harder: there are now two audit artefacts a deployment has to retain and
protect, not one, and the verifier carries a dependency on the bundled
logrotate naming scheme. A deployment that rotates the audit log under a
different naming convention (for example `dateext`) needs a matching segment
reader, or it will read pre-rotation anchors as `unverifiable`. The guarantee
is also bounded by retention: anchors whose pinned content has aged out of
the on-disk segments cannot be verified, which is correct (the evidence is
gone) but means the property is "no undetected truncation within the
retention window," not "ever."

Two limits stay explicit. The anchor is evidence, not access control: like
the chain it supplements `chattr +a` and off-host shipping rather than
replacing them, and an attacker who can rewrite both files consistently can
still forge a clean pair. And the chain is single-writer by construction (one
`nous.service`, one audit file, one anchor file); the multi-writer case
remains out of scope until the multi-tenant track (BL-045).

Alternatives rejected:

- **Sign the daily head.** Stronger (authenticity, not just evidence), but it
  pulls in key management and rotation, which ADR 0025 already deferred to
  BL-059. The anchor is the unsigned, in-band step that stands on its own.
- **Anchor inside the audit log itself.** A periodic "anchor" record in the
  same file does not survive truncation of that file, so it cannot detect the
  very thing it is for. The anchor has to be a separate artefact.
- **Anchor on the tick cadence instead of the tool-call cadence.** The audit
  chain only advances on a tool call, so a tick-driven anchor on a quiet day
  would re-pin an unchanged head. Pinning when the chain actually moves is the
  honest coupling.

## Revisit triggers

- The audit log adopts a rotation scheme the segment reader does not
  understand (`dateext`, a different suffix, a different compressor). The
  reader in `audit_anchor.py` needs to learn that layout, or pre-rotation
  anchors silently degrade to `unverifiable`.
- A regulator asks for signed anchors. Grow `anchor_hash` into a signature
  over the head, aligned to BL-059's key-management decision.
- The audit log becomes multi-writer (multi-tenant, BL-045). A single
  single-writer anchor chain no longer holds; the design needs per-writer
  anchors or a serialising sink.
- The daily reconstruction read shows up as a cost on a very large retained
  set. A bounded tail read of the active segment (plus the recorded
  chained-count) replaces the full multi-segment walk for the common case.
