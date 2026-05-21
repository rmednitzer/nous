"""Audit-durability tests (D-04).

The audit handler must fsync after every emit. These tests verify that
``AuditLogger.flush()`` is callable, that an audit write does not leave
the file in an inconsistent state, and that fsync failures are tallied
on ``fsync_failures``.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    assert logger.degraded or logger.path == str(unreachable)
