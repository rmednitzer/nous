"""Audit hash-chain behaviour (ADR 0025 / BL-016).

The chain links each audit line to the one before it so a verifier can
prove the trail is intact and locate the first tampered line. These tests
pin the four properties the chain promises: every written line is chained,
an intact log verifies, mutation / deletion / reordering are caught, and
the chain head survives a process restart.
"""

from __future__ import annotations

import json
from pathlib import Path

from nous.audit import _GENESIS_HASH, AuditLogger, AuditRecord, verify_chain
from nous.policy import Tier, classify


def _record(tool: str = "device_info", output: str = "ok") -> AuditRecord:
    return AuditRecord.from_output(tool=tool, tier=0, args={"x": 1}, output=output)


def _write_n(logger: AuditLogger, n: int) -> None:
    for i in range(n):
        logger.write(_record(output=f"body-{i}"))


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").strip().splitlines()


def test_first_record_links_to_genesis(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.write(_record())

    obj = json.loads(_read_lines(path)[-1])
    assert obj["prev_hash"] == _GENESIS_HASH
    assert obj["entry_hash"] and obj["entry_hash"] != _GENESIS_HASH


def test_successive_records_form_a_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    _write_n(logger, 3)

    lines = [json.loads(line) for line in _read_lines(path)]
    assert lines[1]["prev_hash"] == lines[0]["entry_hash"]
    assert lines[2]["prev_hash"] == lines[1]["entry_hash"]


def test_verify_passes_for_intact_log(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    _write_n(logger, 5)

    report = verify_chain(path)
    assert report["ok"] is True
    assert report["from_genesis"] is True
    assert report["lines"] == 5
    assert report["chained"] == 5
    assert report["legacy"] == 0
    assert report["first_break_line"] is None
    assert report["head"] == logger.summary()["chain_head"]


def test_verify_detects_in_place_mutation(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    _write_n(logger, 4)

    lines = _read_lines(path)
    tampered = json.loads(lines[1])
    tampered["tool"] = "exfiltrate"
    lines[1] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify_chain(path)
    assert report["ok"] is False
    assert report["first_break_line"] == 2
    assert "entry_hash" in report["reason"]


def test_verify_detects_mid_stream_deletion(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    _write_n(logger, 4)

    lines = _read_lines(path)
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify_chain(path)
    assert report["ok"] is False
    assert report["first_break_line"] == 2
    assert "prev_hash" in report["reason"]


def test_verify_detects_reordering(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    _write_n(logger, 4)

    lines = _read_lines(path)
    lines[1], lines[2] = lines[2], lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify_chain(path)
    assert report["ok"] is False
    assert report["first_break_line"] == 2


def test_verify_skips_legacy_prefix(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    legacy = [
        json.dumps({"tool": "device_info", "tier": 0, "output_sha256": "abc"}),
        json.dumps({"tool": "power_status", "tier": 0, "output_sha256": "def"}),
    ]
    path.write_text("\n".join(legacy) + "\n", encoding="utf-8")

    logger = AuditLogger(path)
    _write_n(logger, 3)

    report = verify_chain(path)
    assert report["ok"] is True
    assert report["legacy"] == 2
    assert report["chained"] == 3
    assert report["lines"] == 5


def test_verify_flags_unchained_line_after_chain_start(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    _write_n(logger, 2)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"tool": "injected", "tier": 0}) + "\n")

    report = verify_chain(path)
    assert report["ok"] is False
    assert report["first_break_line"] == 3
    assert "unchained" in report["reason"]


def test_front_truncation_keeps_linkage_but_drops_from_genesis(tmp_path: Path) -> None:
    """A continuation segment (post-rotation) or a front-truncated log
    still links internally, so ``ok`` stays True; only ``from_genesis``
    drops. This is what keeps routine log rotation from reading as
    tampering, and it is the documented limit (truncation needs the
    BL-031 anchor, not the chain)."""
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    _write_n(logger, 4)

    lines = _read_lines(path)
    del lines[0]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify_chain(path)
    assert report["ok"] is True
    assert report["from_genesis"] is False
    assert report["chained"] == 3


def test_chain_head_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    first = AuditLogger(path)
    _write_n(first, 3)
    head_before = first.summary()["chain_head"]

    revived = AuditLogger(path)
    assert revived.summary()["chain_head"] == head_before

    revived.write(_record(output="after-restart"))
    lines = [json.loads(line) for line in _read_lines(path)]
    assert lines[3]["prev_hash"] == head_before
    assert verify_chain(path)["ok"] is True


def test_summary_reports_genesis_head_on_fresh_log(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit.jsonl")
    assert logger.summary()["chain_head"] == _GENESIS_HASH


def test_verify_missing_file_is_empty_ok(tmp_path: Path) -> None:
    report = verify_chain(tmp_path / "nope.jsonl")
    assert report["ok"] is True
    assert report["lines"] == 0
    assert report["head"] == _GENESIS_HASH


def test_audit_verify_classified_read_only() -> None:
    tier, _ = classify("audit_verify", {})
    assert tier is Tier.READ_ONLY
