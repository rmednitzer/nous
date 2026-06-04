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


def _reconstruct(audit_path: str | Path) -> _Walk:
    """Walk every on-disk audit segment, oldest first, as one logical chain.

    Mirrors :func:`nous.audit.verify_chain` (linkage + recompute + the
    legacy-prefix rule) but spans the rotation siblings and returns the
    ordered list of chained ``entry_hash`` values so the anchor cross-check
    can test membership. A pre-chain (legacy) prefix is tolerated only at
    the very start, exactly as the single-file verifier does.
    """
    segments = _segment_paths(audit_path)
    seg_names = [str(path) for path in segments]
    heads: list[str] = []
    legacy = 0
    from_genesis = False
    expected_prev: str | None = None
    seen_chained = False

    for segment in segments:
        for line in _iter_segment_lines(segment):
            obj = _loads(line)
            if obj is None:
                return _Walk(
                    heads, from_genesis, False,
                    "audit line is not a JSON object", legacy, seg_names,
                )
            recorded = obj.get("entry_hash")
            if not recorded:
                if seen_chained:
                    return _Walk(
                        heads, from_genesis, False,
                        "unchained line after the chain started", legacy, seg_names,
                    )
                legacy += 1
                continue
            body = {key: value for key, value in obj.items() if key != "entry_hash"}
            if _entry_hash(body) != recorded:
                return _Walk(
                    heads, from_genesis, False,
                    "entry_hash does not match record body", legacy, seg_names,
                )
            prev = obj.get("prev_hash", "")
            if expected_prev is None:
                from_genesis = prev == _GENESIS_HASH
                if legacy > 0 and not from_genesis:
                    return _Walk(
                        heads, from_genesis, False,
                        "first chained line after a legacy prefix is not rooted at genesis",
                        legacy, seg_names,
                    )
            elif prev != expected_prev:
                return _Walk(
                    heads, from_genesis, False,
                    "prev_hash does not match the prior link", legacy, seg_names,
                )
            seen_chained = True
            recorded_str = str(recorded)
            heads.append(recorded_str)
            expected_prev = recorded_str

    return _Walk(heads, from_genesis, True, "", legacy, seg_names)


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
        """
        moment = now or datetime.now(UTC)
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
    reconstructed across rotation segments (linkage + recompute). Finally
    every anchored head is tested for membership in that chain. Retention
    drops the oldest content first, so an anchor that is absent while an
    *older* anchor is still present means newer records were removed (tail
    truncation); an anchor absent before any present anchor, once the chain
    no longer roots at genesis, was rotated out and is reported
    ``unverifiable`` rather than as a false break. When the chain still roots
    at genesis (nothing rotated out), any absent anchor is a hard break.

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
    # an absent head means the chain was cut at or before it. Retention
    # removes the oldest content first, so the legitimate "absent" case is an
    # anchor older than every retained record. An anchor absent while an
    # *older* anchor is still present is therefore the truncation signal:
    # newer content was removed out of order.
    present = {head: index for index, head in enumerate(walk.heads)}
    last_index = -1
    seen_present = False
    for anchor in anchors:
        index = present.get(anchor.head)
        if index is not None:
            if index < last_index:
                reason = f"anchor for {anchor.day} head appears out of order (records reordered)"
                report["ok"] = False
                report["first_break"] = {"day": anchor.day, "reason": reason}
                report["reason"] = reason
                return report
            last_index = index
            seen_present = True
            report["checked"] += 1
            continue
        # absent
        if walk.from_genesis:
            if anchor.chained > len(walk.heads):
                reason = (
                    f"anchor for {anchor.day} pinned {anchor.chained} chained records; "
                    f"the audit chain now has {len(walk.heads)} (tail truncation)"
                )
            else:
                reason = (
                    f"anchor for {anchor.day} head is absent from an intact chain "
                    "(history diverged, or the anchor belongs to a different log)"
                )
            report["ok"] = False
            report["first_break"] = {"day": anchor.day, "reason": reason}
            report["reason"] = reason
            return report
        if seen_present:
            reason = (
                f"anchor for {anchor.day} head is absent while an earlier anchor is "
                "still present (tail truncation of newer records)"
            )
            report["ok"] = False
            report["first_break"] = {"day": anchor.day, "reason": reason}
            report["reason"] = reason
            return report
        report["unverifiable"] += 1

    if report["unverifiable"] and report["checked"] == 0:
        report["reason"] = (
            "all anchors predate the oldest retained audit segment; "
            "cannot verify (rotated out of the retention window)"
        )
    return report
