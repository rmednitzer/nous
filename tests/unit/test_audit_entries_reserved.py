"""The SQLite `audit_entries` table is reserved schema, not a live mirror.

BL-065 / ADR 0002 (2026-06-05 update): the authoritative audit trail is the
JSONL sink (`AuditLogger`); `state_transitions` is the live SQLite surface.
The `audit_entries` table is created by the schema but never written by the
audit path. These tests pin that decision so a future half-wired mirror is
caught rather than shipped silently.
"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from nous.audit import AuditLogger, AuditRecord
from nous.db import AuditEntry, StateTransition, StateTransitionLog, init_db


def test_audit_entries_table_exists_in_schema(tmp_path: Path) -> None:
    # The reserved table ships in the baseline so the mirror can be wired later
    # without a migration: the schema is present, just unused.
    engine = init_db(f"sqlite:///{tmp_path / 'state.db'}")
    assert "audit_entries" in AuditEntry.metadata.tables
    with Session(engine) as session:
        assert session.exec(select(AuditEntry)).all() == []


def test_live_audit_path_writes_jsonl_only_not_audit_entries(tmp_path: Path) -> None:
    # A representative workflow: the JSONL sink takes the audit record and the
    # transition log takes the FSM transition. The reserved `audit_entries`
    # table stays empty; `state_transitions` (the live mirror) does not.
    engine = init_db(f"sqlite:///{tmp_path / 'state.db'}")
    audit_path = tmp_path / "audit.jsonl"
    audit = AuditLogger(audit_path)
    transitions = StateTransitionLog(engine)

    audit.write(
        AuditRecord.from_output(tool="device_info", tier=0, args={}, output="{}")
    )
    transitions.append(from_mode="stowed", to_mode="boot", trigger="boot")

    with Session(engine) as session:
        audit_rows = session.exec(select(AuditEntry)).all()
        transition_rows = session.exec(select(StateTransition)).all()

    assert audit_rows == []  # reserved: never written by the live path
    assert len(transition_rows) == 1  # live: transitions are mirrored to SQLite
    # The JSONL sink is the authoritative audit trail and did record the event.
    assert audit_path.read_text(encoding="utf-8").strip()
