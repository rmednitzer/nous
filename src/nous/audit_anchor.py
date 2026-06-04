"""Daily anchor over the audit hash chain (BL-031, ADR 0026).

The BL-016 hash chain (ADR 0025) links each audit line to its predecessor,
so a mutation or a mid-stream deletion breaks a link that ``verify_chain``
reports. What the chain alone cannot catch is *tail truncation*: dropping
the most recent records leaves a shorter chain that is still internally
consistent, so ``verify_chain`` still passes (see LIMITATIONS L18).

This module closes that gap with an external anchor. At most once per UTC
day, :meth:`AnchorLog.maybe_anchor` records the current chain head (a
fingerprint of the entire history) plus the chained-record count into a
*separate* append-only file, itself a hash chain so the anchors cannot be
edited undetected. :func:`verify_anchors` then cross-checks the anchors
against the audit log: an anchored head that is no longer present in the
chain means the trail was truncated below the point the anchor pinned.

The anchor file sits beside the audit log
(``$NOUS_HOME/audit-anchors.jsonl`` by default). It is a second artefact a
deployment ships off-host and makes append-only with ``chattr +a``, raising
the cost of erasing recent evidence to tampering with two files
consistently rather than one.

Rotation: the verifier reconstructs the chain across the conventional
logrotate siblings (``audit.jsonl``, ``audit.jsonl.1``, ``audit.jsonl.2.gz``
and upward) oldest first, so an anchor taken before a rotation still
verifies as long as the segment it pinned is still on disk. Anchors that
predate the oldest retained segment read as ``unverifiable`` (a soft note),
never as a false truncation.
"""

from __future__ import annotations

import gzip
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, NamedTuple

from pydantic import BaseModel, ValidationError

# Reuse the audit chain's canonical hashing so the anchor chain commits to
# its records exactly the way the audit chain commits to its own (one
# hashing discipline). Reading these private names is the correct coupling:
# an anchor that hashed differently could not cross-check the audit chain.
from .audit import _GENESIS_HASH, _entry_hash

__all__ = ["AnchorLog", "AnchorRecord", "verify_anchors"]


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


class AnchorRecord(BaseModel):
    """One daily anchor over the audit hash chain.

    ``head`` is the audit chain head (the most recent ``entry_hash``) as of
    the moment the anchor was taken; ``chained`` is how many chained audit
    records existed then. Together they pin a point in the chain a verifier
    can later confirm is still present. ``prev_anchor_hash`` / ``anchor_hash``
    chain the anchors to each other so the anchor file is itself
    tamper-evident.
    """

    day: str
    ts: str
    audit_path: str
    head: str
    chained: int
    lines: int
    chain_ok: bool
    prev_anchor_hash: str = _GENESIS_HASH
    anchor_hash: str = ""

    def compute_hash(self) -> str:
        body = self.model_dump(mode="json", exclude={"anchor_hash"})
        return _entry_hash(body)


class _Walk(NamedTuple):
    """Result of reconstructing the audit chain across rotation segments."""

    heads: list[str]
    from_genesis: bool
    ok: bool
    reason: str
    legacy: int
    segments: list[str]


def _segment_paths(audit_path: str | Path) -> list[Path]:
    """Conventional logrotate siblings, oldest first, that exist on disk.

    logrotate with ``compress`` + ``delaycompress`` (see
    ``deploy/logrotate.conf``) yields ``audit.jsonl`` (active),
    ``audit.jsonl.1`` (uncompressed), and ``audit.jsonl.2.gz`` upward. The
    chain runs oldest to newest, i.e. highest numeric suffix first, then
    ``.1``, then the active file. Siblings whose suffix is not a bare
    integer (the anchor file, the SQLite db, the WAL) are ignored.
    """
    active = Path(audit_path).expanduser()
    parent = active.parent
    prefix = active.name + "."
    rotated: list[tuple[int, Path]] = []
    if parent.exists():
        for sibling in parent.iterdir():
            name = sibling.name
            if not name.startswith(prefix):
                continue
            suffix = name[len(prefix):]
            if suffix.endswith(".gz"):
                suffix = suffix[:-3]
            if suffix.isdigit():
                rotated.append((int(suffix), sibling))
    rotated.sort(key=lambda item: item[0], reverse=True)
    ordered = [path for _, path in rotated]
    if active.exists():
        ordered.append(active)
    return ordered


def _nonblank(handle: IO[str]) -> Iterator[str]:
    for raw in handle:
        stripped = raw.strip()
        if stripped:
            yield stripped


def _iter_segment_lines(path: Path) -> Iterator[str]:
    """Yield non-blank stripped lines from a segment, transparently gunzipping."""
    if path.suffix == ".gz":
        with gzip.open(path, mode="rt", encoding="utf-8", errors="replace") as handle:
            yield from _nonblank(handle)
    else:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            yield from _nonblank(handle)


def _loads(line: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _first_link_error(prev: str, prev_head: str | None, seg_legacy: int, index: int) -> str:
    """Validate the first chained record of a segment; "" means valid.

    A segment's first chained record may root at genesis (a fresh chain, or a
    post-restart segment whose recovered head was genesis). If a pre-chain
    (legacy) prefix precedes it, it must root at genesis, matching
    ``verify_chain`` (a non-genesis link there is a deletion at the upgrade
    boundary). A later segment with no legacy prefix must either root at
    genesis (restart) or link to the previous segment's last head
    (continuation); anything else is a dangling link left by a deletion at the
    rotation boundary. The oldest retained segment with no legacy prefix has
    no earlier reference, so its first record is accepted as the retained
    boundary (its ``prev`` only sets ``from_genesis``).
    """
    if seg_legacy > 0:
        if prev != _GENESIS_HASH:
            return "first chained line after a legacy prefix is not rooted at genesis"
        return ""
    if index > 0 and prev not in (_GENESIS_HASH, prev_head):
        return "dangling first link at a segment boundary (records deleted at rotation)"
    return ""


def _reconstruct(audit_path: str | Path) -> _Walk:
    """Walk every on-disk audit segment, oldest first, and collect the heads.

    Each segment (the active file and its logrotate siblings) is verified
    mirroring :func:`nous.audit.verify_chain` per file: recompute every
    ``entry_hash``, check ``prev_hash`` linkage within the segment, and
    tolerate a pre-chain (legacy) prefix only at the segment's own start. At a
    segment boundary the first record must root at genesis (a logrotate
    followed by a restart leaves the recovered head at genesis, so the new
    active file is a fresh genesis-rooted segment) or continue from the
    previous segment's head; a link to anything else is a dangling reference
    left by a deletion at the boundary. The oldest retained segment has no
    earlier reference, so its first record sets ``from_genesis`` and is
    otherwise accepted.

    The ordered union of chained ``entry_hash`` values (across all segments)
    is what the anchor cross-check tests for membership. A segment that is
    unreadable, a corrupt ``.gz`` payload, or an unlistable audit directory is
    reported as a structured break, never allowed to escape as an exception.
    """
    heads: list[str] = []
    total_legacy = 0
    oldest_from_genesis = False

    try:
        segments = _segment_paths(audit_path)
    except OSError as exc:
        return _Walk(heads, False, False, f"cannot list audit directory: {exc}", 0, [])
    seg_names = [str(path) for path in segments]

    def _break(reason: str) -> _Walk:
        return _Walk(heads, oldest_from_genesis, False, reason, total_legacy, seg_names)

    for index, segment in enumerate(segments):
        expected_prev: str | None = None
        seg_legacy = 0
        try:
            for line in _iter_segment_lines(segment):
                obj = _loads(line)
                if obj is None:
                    return _break("audit line is not a JSON object")
                recorded = obj.get("entry_hash")
                if not recorded:
                    if expected_prev is not None:
                        return _break("unchained line after the chain started")
                    seg_legacy += 1
                    total_legacy += 1
                    continue
                body = {key: value for key, value in obj.items() if key != "entry_hash"}
                if _entry_hash(body) != recorded:
                    return _break("entry_hash does not match record body")
                prev = obj.get("prev_hash", "")
                if expected_prev is None:
                    error = _first_link_error(prev, heads[-1] if heads else None, seg_legacy, index)
                    if error:
                        return _break(error)
                    if index == 0:
                        oldest_from_genesis = prev == _GENESIS_HASH
                elif prev != expected_prev:
                    return _break("prev_hash does not match the prior link")
                recorded_str = str(recorded)
                heads.append(recorded_str)
                expected_prev = recorded_str
        except (OSError, EOFError) as exc:
            return _break(f"cannot read audit segment {segment.name}: {exc}")

    return _Walk(heads, oldest_from_genesis, True, "", total_legacy, seg_names)


def _read_anchors(
    anchor_path: str | Path,
) -> tuple[list[AnchorRecord], bool, str, dict[str, Any] | None]:
    """Parse the anchor file and verify the anchors' own hash chain.

    Returns ``(anchors, ok, reason, first_break)``. A missing file is a
    clean empty result (no anchors recorded yet). A tampered anchor line, a
    broken anchor-to-anchor link, or a schema failure sets ``ok`` false and
    localises the break.
    """
    target = Path(anchor_path).expanduser()
    anchors: list[AnchorRecord] = []

    def _fail(
        reason: str, line_no: int, day: str
    ) -> tuple[list[AnchorRecord], bool, str, dict[str, Any]]:
        return anchors, False, reason, {"day": day, "line": line_no, "reason": reason}

    if not target.exists():
        return anchors, True, "", None

    try:
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            raw_lines = [stripped for stripped in (line.strip() for line in handle) if stripped]
    except OSError as exc:
        return _fail(f"cannot open anchor log: {exc}", 0, "")

    expected_prev = _GENESIS_HASH
    for line_no, line in enumerate(raw_lines, start=1):
        obj = _loads(line)
        if obj is None:
            return _fail("anchor line is not a JSON object", line_no, "")
        day = str(obj.get("day", ""))
        recorded = obj.get("anchor_hash")
        if not recorded or not isinstance(recorded, str):
            return _fail("anchor line missing anchor_hash", line_no, day)
        body = {key: value for key, value in obj.items() if key != "anchor_hash"}
        if _entry_hash(body) != recorded:
            return _fail("anchor_hash does not match record body", line_no, day)
        if obj.get("prev_anchor_hash", "") != expected_prev:
            return _fail("prev_anchor_hash does not match the prior anchor", line_no, day)
        try:
            anchors.append(AnchorRecord.model_validate(obj))
        except ValidationError:
            return _fail("anchor line failed schema validation", line_no, day)
        expected_prev = recorded

    return anchors, True, "", None


class AnchorLog:
    """Append-only daily anchor over the audit hash chain. Never raises on write."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.writes_total = 0
        self.degraded = False
        self.degraded_reason = ""
        self._anchor_head = _GENESIS_HASH
        self._last_day = ""
        self._recover()

    def _recover(self) -> None:
        """Re-ground the anchor head and last-anchored day from the file tail.

        Lets the daily cadence survive a process restart: a box that already
        anchored today will not write a duplicate after a bounce.
        """
        last = ""
        try:
            target = Path(self.path).expanduser()
            if not target.exists():
                return
            with target.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    stripped = line.strip()
                    if stripped:
                        last = stripped
            if not last:
                return
            obj = json.loads(last)
        except (OSError, ValueError):
            return
        if isinstance(obj, dict):
            head = obj.get("anchor_hash")
            day = obj.get("day")
            if isinstance(head, str) and head:
                self._anchor_head = head
            if isinstance(day, str) and day:
                self._last_day = day

    def maybe_anchor(
        self, audit_path: str | Path, *, now: datetime | None = None
    ) -> AnchorRecord | None:
        """Write one anchor if the UTC day has rolled over since the last one.

        Cheap on the common path (a single date comparison); on the first
        call of a new UTC day it reconstructs the audit chain to capture the
        head and chained-record count, then appends one anchor. Returns the
        record it wrote, or ``None`` when nothing was due (same day, an empty
        chain, or a failed append).

        ``now`` is normalized to UTC before the day is taken (an aware value
        is converted, a naive value is assumed to be UTC), so the cadence is
        the UTC calendar day regardless of the caller's timezone.
        """
        moment = now if now is not None else datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        moment = moment.astimezone(UTC)
        day = moment.date().isoformat()
        if day == self._last_day:
            return None

        walk = _reconstruct(audit_path)
        if not walk.heads:
            # Nothing chained yet (fresh or degraded sink). Do not advance
            # the day marker, so the next call re-checks once a record lands.
            return None

        record = AnchorRecord(
            day=day,
            ts=_iso(moment),
            audit_path=str(audit_path),
            head=walk.heads[-1],
            chained=len(walk.heads),
            lines=len(walk.heads) + walk.legacy,
            chain_ok=walk.ok,
            prev_anchor_hash=self._anchor_head,
        )
        record.anchor_hash = record.compute_hash()
        if not self._append(record):
            return None
        self._anchor_head = record.anchor_hash
        self._last_day = day
        self.writes_total += 1
        return record

    def _append(self, record: AnchorRecord) -> bool:
        try:
            target = Path(self.path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            self.degraded = True
            self.degraded_reason = str(exc)
            return False
        self.degraded = False
        self.degraded_reason = ""
        return True

    def summary(self) -> dict[str, Any]:
        """Read-only view of the anchor log state, for ``device_info``."""
        return {
            "path": self.path,
            "last_anchored_day": self._last_day,
            "anchor_head": self._anchor_head,
            "writes_total": self.writes_total,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
        }


def verify_anchors(audit_path: str | Path, anchor_path: str | Path) -> dict[str, Any]:
    """Cross-check the daily anchors against the audit chain (BL-031).

    Detects tail truncation the BL-016 hash chain cannot: each anchor pins a
    head (a fingerprint of the whole history to that point), so an anchored
    head that is no longer present in the reconstructed chain means the
    trail was cut below the anchor.

    The check has three layers. The anchor file's own hash chain is verified
    first (a tampered anchor is itself evidence). The audit chain is then
    reconstructed across rotation segments, each verified independently
    (linkage + recompute per segment; segments need not link to each other,
    since a rotate-plus-restart legitimately restarts the chain at genesis).
    Finally every anchored head is tested for membership in the union of
    segment heads. The newest anchor must always be present (it pins recent
    activity that is within retention, so its absence is tail truncation,
    including the case where the active log was wiped and new records link to
    a stale head). Older anchors that form a contiguous absent prefix were
    rotated out of the retention window and are reported ``unverifiable``; an
    anchor absent after a present one means newer content was removed out of
    order, which is a break.

    Never raises. Returns a JSON-safe report::

        {
            "audit_path": "...", "anchor_path": "...",
            "ok": true,                # anchors consistent with the chain
            "anchors": 3,              # anchors read
            "checked": 3,              # anchors confirmed present
            "unverifiable": 0,         # anchors predating retained segments
            "anchor_chain_ok": true,   # the anchor file's own chain is intact
            "audit_chain_ok": true,    # the reconstructed audit chain is intact
            "from_genesis": true,      # the retained chain roots at genesis
            "audit_chained": 42,       # chained records across all segments
            "head": "<hex>",           # current chain head
            "first_break": null,       # {"day", "reason"} of the first failure
            "reason": "",
        }
    """
    report: dict[str, Any] = {
        "audit_path": str(Path(audit_path).expanduser()),
        "anchor_path": str(Path(anchor_path).expanduser()),
        "ok": True,
        "anchors": 0,
        "checked": 0,
        "unverifiable": 0,
        "anchor_chain_ok": True,
        "audit_chain_ok": True,
        "from_genesis": False,
        "audit_chained": 0,
        "head": _GENESIS_HASH,
        "first_break": None,
        "reason": "",
    }

    anchors, anchor_ok, anchor_reason, anchor_break = _read_anchors(anchor_path)
    report["anchors"] = len(anchors)
    report["anchor_chain_ok"] = anchor_ok
    if not anchor_ok:
        report["ok"] = False
        report["reason"] = f"anchor chain broken: {anchor_reason}"
        report["first_break"] = anchor_break
        return report

    walk = _reconstruct(audit_path)
    report["audit_chain_ok"] = walk.ok
    report["from_genesis"] = walk.from_genesis
    report["audit_chained"] = len(walk.heads)
    report["head"] = walk.heads[-1] if walk.heads else _GENESIS_HASH
    if not walk.ok:
        report["ok"] = False
        report["reason"] = f"audit chain broken: {walk.reason}"
        return report

    if not anchors:
        report["reason"] = "no anchors recorded yet"
        return report

    # Membership is the cross-check: each anchored head commits to its whole
    # prefix, so a present-and-linked head proves that prefix is intact, and
    # an absent head means the chain was cut at or before it.
    #
    # The newest anchor must always be present. It pins the most recent UTC
    # day with audit activity, which lives in the active (or near-active)
    # segment and is therefore always within retention; if it is gone, the
    # tail was truncated (the realistic attack: wipe the active log to erase
    # recent actions, where the records then link to a stale in-memory head
    # and contain none of the anchored heads). Among the older anchors,
    # retention removes the oldest content first, so a contiguous prefix of
    # absent anchors is the legitimate "rotated out of the window" case
    # (``unverifiable``); an anchor absent *after* a present one means newer
    # content was removed out of order, which is truncation.
    present = {head: index for index, head in enumerate(walk.heads)}

    def _fail(day: str, reason: str) -> dict[str, Any]:
        report["ok"] = False
        report["first_break"] = {"day": day, "reason": reason}
        report["reason"] = reason
        return report

    newest = anchors[-1]
    if newest.head not in present:
        return _fail(
            newest.day,
            f"most recent anchor ({newest.day}) head is absent from the retained "
            "chain (tail truncation of recent records)",
        )

    last_index = -1
    seen_present = False
    for anchor in anchors:
        index = present.get(anchor.head)
        if index is None:
            if seen_present:
                return _fail(
                    anchor.day,
                    f"anchor for {anchor.day} head is absent while an earlier anchor "
                    "is still present (tail truncation of newer records)",
                )
            report["unverifiable"] += 1
            continue
        if index < last_index:
            return _fail(
                anchor.day,
                f"anchor for {anchor.day} head appears out of order (records reordered)",
            )
        last_index = index
        seen_present = True
        report["checked"] += 1

    if report["unverifiable"]:
        report["reason"] = (
            f"{report['unverifiable']} anchor(s) predate the oldest retained audit "
            "segment and could not be verified (rotated out of the retention window)"
        )
    return report
