"""SQLite-backed persistence with WAL journalling.

The simulator writes each admitted state-machine transition (and each guard
refusal) to the live ``state_transitions`` table; rows are written per
transition, not per tick. The ``audit_entries`` table is reserved schema,
not a live mirror: the authoritative audit trail is the append-only JSONL sink
(``nous.audit.AuditLogger``). See :class:`AuditEntry` and ADR 0002 (BL-065).
The default database lives at ``$NOUS_HOME/state.db`` and is opened with WAL so
reads and writes do not block each other.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, desc, event
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, select

__all__ = [
    "AuditEntry",
    "StateTransition",
    "StateTransitionLog",
    "init_db",
    "make_engine",
]


class StateTransition(SQLModel, table=True):
    __tablename__ = "state_transitions"

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    from_mode: str
    to_mode: str
    trigger: str
    reason: str = ""


class AuditEntry(SQLModel, table=True):
    """Reserved schema for a future SQLite mirror of the JSONL audit log.

    Not live (BL-065): nothing in the engine or the audit path instantiates
    ``AuditEntry``. The authoritative audit trail is the append-only JSONL sink
    (``nous.audit.AuditLogger``), which ships off-host and carries the BL-016
    hash chain and the BL-031 daily anchor; duplicating it into SQLite would
    add a second tamper surface and a sync invariant for no current consumer
    (the audit tools read the JSONL, and only ``state_transitions`` is queried
    from SQLite). The Alembic baseline still creates the table so the schema is
    ready; the mirror is wired later, carrying ``prev_hash`` / ``entry_hash``
    so both surfaces verify, only if a controller needs SQL over the audit
    (ADR 0002, 2026-06-05 update).
    """

    __tablename__ = "audit_entries"

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tool: str
    tier: int
    denied: bool = False
    output_sha256: str
    output_len: int
    exit_code: int | None = None
    request_id: str = ""
    client_id: str = ""


def _enable_wal(dbapi_conn: Any, _record: Any) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def make_engine(url: str) -> Engine:
    """Construct a SQLAlchemy engine with WAL enabled for SQLite URLs."""
    engine = create_engine(url, future=True)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_wal)
    return engine


def init_db(url: str, *, ensure_parent: bool = True) -> Engine:
    """Create tables (idempotent). Used at first boot and in tests."""
    if ensure_parent and url.startswith("sqlite:///"):
        path = Path(url[len("sqlite:///") :])
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    SQLModel.metadata.create_all(engine)
    return engine


class StateTransitionLog:
    """Append + tail-query wrapper around ``StateTransition`` rows (BL-017).

    The engine constructs one of these per process and calls
    :meth:`append` whenever the FSM admits a transition. The
    ``state_history`` MCP tool calls :meth:`tail` to read the last
    ``limit`` rows. Append failures degrade silently so a flaky DB
    cannot prevent the engine from advancing -- consistent with the
    audit logger's "best effort" posture.
    """

    def __init__(self, engine: Engine | None) -> None:
        self.engine = engine
        self.append_failures = 0
        self.last_error = ""

    def append(
        self,
        *,
        from_mode: str,
        to_mode: str,
        trigger: str,
        reason: str = "",
    ) -> None:
        if self.engine is None:
            return
        row = StateTransition(
            from_mode=from_mode,
            to_mode=to_mode,
            trigger=trigger,
            reason=reason,
        )
        try:
            with Session(self.engine) as session:
                session.add(row)
                session.commit()
        except Exception as exc:  # noqa: BLE001
            self.append_failures += 1
            self.last_error = f"{exc.__class__.__name__}: {exc}"

    def tail(self, limit: int = 16) -> list[StateTransition]:
        """Return the most recent ``limit`` rows, oldest first."""
        if self.engine is None:
            return []
        n = max(1, min(limit, 1024))
        try:
            with Session(self.engine) as session:
                stmt = (
                    select(StateTransition)
                    .order_by(desc("id"))
                    .limit(n)
                )
                rows: Iterable[StateTransition] = session.exec(stmt).all()
                return list(reversed(list(rows)))
        except Exception as exc:  # noqa: BLE001
            self.append_failures += 1
            self.last_error = f"{exc.__class__.__name__}: {exc}"
            return []
