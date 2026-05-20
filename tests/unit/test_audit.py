"""Audit-log behaviour: JSONL append, SHA-256, redaction, no body bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nous.audit import AuditLogger, AuditRecord, redact


def test_redact_masks_sensitive_keys() -> None:
    args = {"Authorization": "Bearer x", "command": "ls", "password": "hunter2"}
    out = redact(args)
    assert out["Authorization"] == "<REDACTED>"
    assert out["password"] == "<REDACTED>"
    assert out["command"] == "ls"


def test_audit_appends_sha256_not_body(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    record = AuditRecord.from_output(
        tool="device_info",
        tier=0,
        args={"x": 1},
        output="hello, audit",
    )
    logger.write(record)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "audit log should have at least one line"
    obj = json.loads(lines[-1])
    assert obj["tool"] == "device_info"
    assert obj["tier"] == 0
    assert obj["output_sha256"] == hashlib.sha256(b"hello, audit").hexdigest()
    assert "output" not in obj
    assert "body" not in obj
