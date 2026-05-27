"""Audit-durability tests (D-04).

The audit handler must fsync after every emit. These tests verify that
``AuditLogger.flush()`` is callable, that an audit write does not leave
the file in an inconsistent state, and that fsync failures are tallied
on ``fsync_failures``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nous.audit import AuditLogger, AuditRecord


def test_audit_flushes_after_write(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    record = AuditRecord.from_output(
        tool="t", tier=0, args={}, output="x"
    )
    logger.write(record)
    # The file must be flushed and fsynced -- reading it from a fresh fd
    # in the same process must yield the line.
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text.strip())["tool"] == "t"


def test_audit_flush_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.flush()
    logger.flush()
    logger.write(AuditRecord.from_output(tool="t", tier=0, args={}, output="x"))
    logger.flush()
    assert path.exists()


def test_audit_degraded_when_directory_unwritable(tmp_path: Path) -> None:
    # If the parent does not exist and cannot be created, the handler
    # falls back to stderr and ``degraded`` is True.
    unreachable = Path("/proc/0/audit.jsonl")
    logger = AuditLogger(unreachable)
    # /proc/0 is not a real directory; expect degraded
    assert logger.degraded


def test_audit_degraded_on_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)

    def _fail_fsync(fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("nous.audit.os.fsync", _fail_fsync)
    logger.write(AuditRecord.from_output(tool="t", tier=0, args={}, output="x"))

    assert logger.degraded
    assert logger.fsync_failures == 1
    assert "simulated fsync failure" in logger.degraded_reason


# --- AUDIT-2026-05-23 N2: in-process audit-sink recovery ---


def test_resync_on_healthy_sink_is_idempotent(tmp_path: Path) -> None:
    """``resync()`` against a healthy sink is a no-op write: the
    handler is reattached, the file stays writable, ``recovered``
    is False because the sink was never degraded."""
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.write(AuditRecord.from_output(tool="t", tier=0, args={}, output="x"))

    result = logger.resync()
    assert result["degraded"] is False
    assert result["recovered"] is False
    assert result["path"] == str(path)

    # The sink still works after a no-op resync.
    logger.write(AuditRecord.from_output(tool="t", tier=0, args={}, output="y"))
    text = path.read_text(encoding="utf-8")
    assert text.count("\n") == 2


def test_resync_recovers_from_degraded_state(tmp_path: Path) -> None:
    """An operator who fixes the underlying filesystem issue can
    clear the degraded state in process via ``resync()`` without
    restarting the service. Closes AUDIT-2026-05-23 N2 (live audit
    sink stuck degraded until process restart)."""
    # Open against an unreachable path so the logger lands in the
    # degraded state.
    unreachable = Path("/proc/0/audit.jsonl")
    logger = AuditLogger(unreachable)
    assert logger.degraded

    # Operator fixes the underlying issue: point the logger at a
    # writable path and call resync. In real life the path stays
    # the same and the operator fixes the filesystem; the test
    # simulates the "underlying cause cleared" condition.
    fixed_path = tmp_path / "audit.jsonl"
    logger.path = str(fixed_path)

    result = logger.resync()
    assert result["degraded"] is False
    assert result["recovered"] is True
    assert result["degraded_reason"] == ""

    # The recovered sink works.
    logger.write(AuditRecord.from_output(tool="t", tier=0, args={}, output="ok"))
    assert fixed_path.read_text(encoding="utf-8").strip() != ""


def test_resync_when_cause_still_present_remains_degraded(tmp_path: Path) -> None:
    """An operator who runs the tool before fixing the cause sees
    the same degraded state. ``recovered`` is False because the
    state did not change."""
    unreachable = Path("/proc/0/audit.jsonl")
    logger = AuditLogger(unreachable)
    assert logger.degraded
    prior_reason = logger.degraded_reason

    result = logger.resync()
    assert result["degraded"] is True
    assert result["recovered"] is False
    # The reason updates (the new attempt has its own error), but
    # the degraded state persists.
    assert result["degraded_reason"]
    assert prior_reason  # original reason was non-empty too


def test_resync_preserves_cumulative_fsync_failure_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``fsync_failures`` is the cumulative counter so an operator
    can still see how many writes were lost during the degraded
    window after recovery. ``resync()`` does NOT reset it."""
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)

    def _fail_fsync(fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("nous.audit.os.fsync", _fail_fsync)
    logger.write(AuditRecord.from_output(tool="t", tier=0, args={}, output="x"))
    assert logger.fsync_failures == 1

    # Stop simulating the failure; resync should recover.
    monkeypatch.undo()
    result = logger.resync()
    assert result["degraded"] is False
    assert result["recovered"] is True
    # Cumulative counter survives the recovery.
    assert result["fsync_failures"] == 1
    assert logger.fsync_failures == 1
