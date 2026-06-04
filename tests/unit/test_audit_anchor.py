"""Daily audit anchor behaviour (BL-031, ADR 0026).

The BL-016 hash chain cannot detect tail truncation: dropping the most
recent records leaves a shorter, still-consistent chain that ``verify_chain``
still passes. The daily anchor closes that gap by pinning the chain head
once per UTC day into a separate, hash-linked file. These tests pin the
properties the anchor promises: at most one anchor per UTC day, the anchor
file is itself tamper-evident, an anchored head that is truncated away is
caught, an audit mutation is caught, and routine logrotate (including the
gzipped tail) does not read as tampering.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from nous.audit import _GENESIS_HASH, AuditLogger, AuditRecord
from nous.audit_anchor import AnchorLog, verify_anchors
from nous.policy import Tier, classify


def _record(output: str = "ok") -> AuditRecord:
    return AuditRecord.from_output(tool="device_info", tier=0, args={"x": 1}, output=output)


def _write_n(logger: AuditLogger, n: int) -> None:
    for i in range(n):
        logger.write(_record(output=f"body-{i}"))


def _day(day_of_june: int) -> datetime:
    return datetime(2026, 6, day_of_june, 12, 0, 0, tzinfo=UTC)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").strip().splitlines()


def test_anchor_written_once_per_utc_day(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 3)

    log = AnchorLog(anchors)
    first = log.maybe_anchor(audit, now=_day(1))
    assert first is not None
    assert first.chained == 3
    # Same UTC day -> no second anchor.
    assert log.maybe_anchor(audit, now=_day(1)) is None

    _write_n(logger, 2)
    second = log.maybe_anchor(audit, now=_day(2))
    assert second is not None
    assert second.chained == 5

    assert len(_lines(anchors)) == 2
    assert first.day == "2026-06-01"
    assert second.day == "2026-06-02"


def test_maybe_anchor_normalizes_now_to_utc(tmp_path: Path) -> None:
    """The cadence is the UTC calendar day regardless of the caller's
    timezone: a wall-clock that is still 'yesterday' locally but past
    midnight UTC anchors on the UTC day, and a second call on the same UTC
    day (different wall clock) does not duplicate."""
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 2)
    log = AnchorLog(anchors)

    # 23:30 at UTC-5 is 04:30 the next day in UTC.
    est = timezone(timedelta(hours=-5))
    first = log.maybe_anchor(audit, now=datetime(2026, 6, 1, 23, 30, tzinfo=est))
    assert first is not None
    assert first.day == "2026-06-02"
    # Same UTC day reached by a different wall clock -> no duplicate.
    assert log.maybe_anchor(audit, now=datetime(2026, 6, 2, 0, 5, 0, tzinfo=UTC)) is None
    # A naive datetime is assumed UTC, so it stays on the same UTC day.
    assert log.maybe_anchor(audit, now=datetime(2026, 6, 2, 9, 0, 0)) is None


def test_anchor_skips_empty_chain(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"  # never written
    anchors = tmp_path / "audit-anchors.jsonl"
    log = AnchorLog(anchors)
    assert log.maybe_anchor(audit, now=_day(1)) is None
    assert not anchors.exists()


def test_anchor_chain_is_hash_linked(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 3)

    log = AnchorLog(anchors)
    first = log.maybe_anchor(audit, now=_day(1))
    _write_n(logger, 1)
    second = log.maybe_anchor(audit, now=_day(2))
    assert first is not None and second is not None

    assert first.prev_anchor_hash == _GENESIS_HASH
    assert first.anchor_hash and first.anchor_hash != _GENESIS_HASH
    assert second.prev_anchor_hash == first.anchor_hash
    # The stored hash recomputes from the record body.
    assert first.compute_hash() == first.anchor_hash
    assert second.compute_hash() == second.anchor_hash


def test_verify_passes_for_intact_log(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 3)
    log = AnchorLog(anchors)
    log.maybe_anchor(audit, now=_day(1))
    _write_n(logger, 2)
    log.maybe_anchor(audit, now=_day(2))

    report = verify_anchors(audit, anchors)
    assert report["ok"] is True
    assert report["anchors"] == 2
    assert report["checked"] == 2
    assert report["unverifiable"] == 0
    assert report["anchor_chain_ok"] is True
    assert report["audit_chain_ok"] is True
    assert report["from_genesis"] is True
    assert report["audit_chained"] == 5
    assert report["first_break"] is None


def test_verify_detects_tail_truncation(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 6)
    log = AnchorLog(anchors)
    anchor = log.maybe_anchor(audit, now=_day(1))
    assert anchor is not None and anchor.chained == 6

    # Drop the most recent three records: the chain that remains is still
    # internally consistent (verify_chain would pass), but the anchored head
    # is gone.
    lines = _lines(audit)
    audit.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert "truncation" in report["reason"]
    assert report["first_break"] == {"day": "2026-06-01", "reason": report["reason"]}


def test_verify_detects_anchor_tampering(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 3)
    log = AnchorLog(anchors)
    log.maybe_anchor(audit, now=_day(1))
    _write_n(logger, 1)
    log.maybe_anchor(audit, now=_day(2))

    # Rewrite the first anchor's pinned head: the anchor's own hash chain
    # must catch it.
    alines = _lines(anchors)
    obj = json.loads(alines[0])
    obj["head"] = "0" * 64
    alines[0] = json.dumps(obj)
    anchors.write_text("\n".join(alines) + "\n", encoding="utf-8")

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert report["anchor_chain_ok"] is False
    assert "anchor chain broken" in report["reason"]


def test_verify_detects_audit_mutation(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 4)
    log = AnchorLog(anchors)
    log.maybe_anchor(audit, now=_day(1))

    lines = _lines(audit)
    tampered = json.loads(lines[1])
    tampered["tool"] = "exfiltrate"
    lines[1] = json.dumps(tampered)
    audit.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert report["audit_chain_ok"] is False
    assert "audit chain broken" in report["reason"]


def test_verify_with_no_anchors_is_ok(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"  # never written
    logger = AuditLogger(audit)
    _write_n(logger, 3)

    report = verify_anchors(audit, anchors)
    assert report["ok"] is True
    assert report["anchors"] == 0
    assert "no anchors" in report["reason"]


def test_last_day_survives_restart(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 2)

    first = AnchorLog(anchors)
    assert first.maybe_anchor(audit, now=_day(1)) is not None

    # A fresh AnchorLog over the same file must recover today's marker so a
    # restart does not write a duplicate anchor for the same UTC day.
    revived = AnchorLog(anchors)
    assert revived.maybe_anchor(audit, now=_day(1)) is None
    assert len(_lines(anchors)) == 1


def test_verify_survives_logrotate_continuation(tmp_path: Path) -> None:
    """A rotation that moves the active file aside and continues the chain
    into a fresh file must still verify: the anchor reconstructs across the
    rotated sibling and finds the anchored head."""
    audit = tmp_path / "audit.jsonl"
    rotated = tmp_path / "audit.jsonl.1"
    anchors = tmp_path / "audit-anchors.jsonl"

    logger = AuditLogger(audit)
    _write_n(logger, 4)
    # logrotate moves the active file; the running handler reopens a fresh
    # active file on the next write and the in-memory chain head continues.
    audit.rename(rotated)
    _write_n(logger, 3)

    log = AnchorLog(anchors)
    anchor = log.maybe_anchor(audit, now=_day(1))
    assert anchor is not None
    assert anchor.chained == 7

    report = verify_anchors(audit, anchors)
    assert report["ok"] is True
    assert report["from_genesis"] is True
    assert report["audit_chained"] == 7
    assert report["checked"] == 1


def test_verify_reconstructs_across_gzipped_segments(tmp_path: Path) -> None:
    """Older segments are gzipped (``audit.jsonl.2.gz``). The verifier must
    read them so an anchor taken over the full chain still verifies."""
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 6)

    # Split the single genesis-rooted chain into three ordered segments,
    # oldest (gzipped) first, exactly as logrotate with compress would leave
    # them on disk.
    rows = _lines(audit)
    with gzip.open(tmp_path / "audit.jsonl.2.gz", "wt", encoding="utf-8") as handle:
        handle.write("\n".join(rows[0:2]) + "\n")
    (tmp_path / "audit.jsonl.1").write_text("\n".join(rows[2:4]) + "\n", encoding="utf-8")
    audit.write_text("\n".join(rows[4:6]) + "\n", encoding="utf-8")

    log = AnchorLog(anchors)
    anchor = log.maybe_anchor(audit, now=_day(1))
    assert anchor is not None
    assert anchor.chained == 6

    report = verify_anchors(audit, anchors)
    assert report["ok"] is True
    assert report["from_genesis"] is True
    assert report["audit_chained"] == 6
    assert report["checked"] == 1


def test_old_anchor_rotated_out_is_unverifiable_when_newer_present(tmp_path: Path) -> None:
    """An old anchor whose pinned content has aged out of the retention
    window reads as ``unverifiable`` (not a false truncation) as long as a
    newer anchor is still present, which is the steady-state case."""
    audit = tmp_path / "audit.jsonl"
    rotated = tmp_path / "audit.jsonl.1"
    anchors = tmp_path / "audit-anchors.jsonl"

    logger = AuditLogger(audit)
    _write_n(logger, 2)
    log = AnchorLog(anchors)
    old = log.maybe_anchor(audit, now=_day(1))  # pins a head that will rotate out

    # Continue the chain, anchor again (a newer head that stays retained),
    # then evict the segment the old anchor pinned.
    audit.rename(rotated)
    _write_n(logger, 3)
    new = log.maybe_anchor(audit, now=_day(2))
    rotated.unlink()
    assert old is not None and new is not None

    report = verify_anchors(audit, anchors)
    assert report["ok"] is True
    assert report["unverifiable"] == 1
    assert report["checked"] == 1


def test_verify_survives_logrotate_plus_restart(tmp_path: Path) -> None:
    """logrotate moves the active file aside; if the service restarts before
    the next write, the recovered head is genesis, so the new active file is
    an independent genesis-rooted segment, not a continuation. Each segment
    is verified on its own, so this routine case must not read as a broken
    chain (Codex P2: tolerate rotation restarts)."""
    audit = tmp_path / "audit.jsonl"
    rotated = tmp_path / "audit.jsonl.1"
    anchors = tmp_path / "audit-anchors.jsonl"

    first = AuditLogger(audit)
    _write_n(first, 4)
    audit.rename(rotated)
    # A fresh AuditLogger over the (now empty) active path == a restart: its
    # recovered head is genesis, so records start a new genesis-rooted chain.
    restarted = AuditLogger(audit)
    _write_n(restarted, 3)

    log = AnchorLog(anchors)
    anchor = log.maybe_anchor(audit, now=_day(1))
    assert anchor is not None
    assert anchor.chained == 7

    report = verify_anchors(audit, anchors)
    assert report["ok"] is True
    assert report["audit_chain_ok"] is True
    assert report["audit_chained"] == 7
    assert report["checked"] == 1


def test_verify_detects_active_log_wiped_while_running(tmp_path: Path) -> None:
    """If the active log is truncated to zero while the service keeps running,
    new records link to the stale in-memory head and contain none of the
    anchored heads. The most-recent-anchor rule must flag this as truncation
    rather than waving it through as ``unverifiable`` (Codex P2)."""
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 4)
    log = AnchorLog(anchors)
    assert log.maybe_anchor(audit, now=_day(1)) is not None

    # Wipe the active file in place; the handler keeps its in-memory head, so
    # the next records link to a head that is no longer on disk.
    audit.write_text("", encoding="utf-8")
    _write_n(logger, 2)

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert "truncation" in report["reason"]
    assert report["first_break"]["day"] == "2026-06-01"


def test_verify_reports_unreadable_segment_as_structured_break(tmp_path: Path) -> None:
    """A corrupt ``.gz`` rotated segment must surface as a structured
    ``audit_chain_ok: false`` report, not an exception that escapes as the
    runner's ``[error ...]`` string (Codex P2)."""
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"
    logger = AuditLogger(audit)
    _write_n(logger, 3)
    log = AnchorLog(anchors)
    log.maybe_anchor(audit, now=_day(1))

    # A rotated segment that claims to be gzip but is not.
    (tmp_path / "audit.jsonl.1.gz").write_bytes(b"this is not a valid gzip payload")

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert report["audit_chain_ok"] is False
    assert "cannot read audit segment" in report["reason"]


def test_verify_detects_truncation_in_steady_state(tmp_path: Path) -> None:
    """In the steady state (front rotated out, several anchors), dropping the
    tail removes a newer anchor's head while an older anchor stays present,
    which is the truncation signal even without a genesis root."""
    audit = tmp_path / "audit.jsonl"
    rotated = tmp_path / "audit.jsonl.1"
    anchors = tmp_path / "audit-anchors.jsonl"

    logger = AuditLogger(audit)
    _write_n(logger, 4)
    # Rotate, then evict the genesis segment so the retained chain is a pure
    # continuation (no genesis root) before any anchor is taken.
    audit.rename(rotated)
    _write_n(logger, 2)
    rotated.unlink()
    log = AnchorLog(anchors)
    older = log.maybe_anchor(audit, now=_day(1))  # pins a head inside the active file
    _write_n(logger, 3)
    newer = log.maybe_anchor(audit, now=_day(2))  # pins a later head
    assert older is not None and newer is not None

    # Drop the most recent records so the newer anchor's head disappears
    # while the older anchor's head survives.
    rows = _lines(audit)
    audit.write_text("\n".join(rows[:2]) + "\n", encoding="utf-8")

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert report["from_genesis"] is False
    assert "truncation" in report["reason"]
    assert report["first_break"]["day"] == "2026-06-02"


def test_verify_detects_deletion_at_rotation_boundary(tmp_path: Path) -> None:
    """Deleting the first records of a later (continuation) segment leaves a
    dangling first link that must be rejected, even if an anchored head later
    in that segment survives (Codex P2)."""
    audit = tmp_path / "audit.jsonl"
    rotated = tmp_path / "audit.jsonl.1"
    anchors = tmp_path / "audit-anchors.jsonl"

    logger = AuditLogger(audit)
    _write_n(logger, 4)
    audit.rename(rotated)  # .1 = records 1-4
    _write_n(logger, 3)  # active = records 5-7 (record 5 links to record 4)
    log = AnchorLog(anchors)
    assert log.maybe_anchor(audit, now=_day(1)) is not None  # pins head 7

    # Delete the first record of the active segment; record 6 now links to the
    # deleted record 5's head -- neither genesis nor the .1 head.
    rows = _lines(audit)
    audit.write_text("\n".join(rows[1:]) + "\n", encoding="utf-8")

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert report["audit_chain_ok"] is False
    assert "dangling" in report["reason"]


def test_verify_detects_deletion_at_legacy_boundary(tmp_path: Path) -> None:
    """A segment that begins with legacy (pre-chain) lines must have its first
    chained record rooted at genesis; deleting that record leaves a
    non-genesis link after the legacy prefix, which is a break (Codex P2,
    mirrors verify_chain)."""
    audit = tmp_path / "audit.jsonl"
    anchors = tmp_path / "audit-anchors.jsonl"

    legacy = json.dumps({"tool": "device_info", "tier": 0, "output_sha256": "abc"})
    audit.write_text(legacy + "\n", encoding="utf-8")
    logger = AuditLogger(audit)
    _write_n(logger, 3)  # first chained record is genesis-rooted after the legacy line
    log = AnchorLog(anchors)
    assert log.maybe_anchor(audit, now=_day(1)) is not None

    rows = _lines(audit)  # [legacy, chained1(genesis), chained2, chained3]
    del rows[1]  # drop the genesis-rooted first chained record
    audit.write_text("\n".join(rows) + "\n", encoding="utf-8")

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert report["audit_chain_ok"] is False
    assert "genesis" in report["reason"]


def test_verify_reports_unlistable_directory_as_structured_break(tmp_path: Path) -> None:
    """If the audit directory cannot be listed (here the parent path is a
    file, not a directory), the verifier returns a structured break rather
    than letting the error escape as the runner's [error ...] string
    (Codex P2)."""
    not_a_dir = tmp_path / "not-a-dir"
    not_a_dir.write_text("x", encoding="utf-8")
    audit = not_a_dir / "audit.jsonl"  # parent is a file
    anchors = tmp_path / "audit-anchors.jsonl"

    report = verify_anchors(audit, anchors)
    assert report["ok"] is False
    assert report["audit_chain_ok"] is False
    assert "cannot list audit directory" in report["reason"]


def test_audit_anchor_verify_classified_read_only() -> None:
    tier, _ = classify("audit_anchor_verify", {})
    assert tier is Tier.READ_ONLY
