"""SQLite-backed persistence with WAL journalling.

The simulator writes per-tick state transitions and one audit-mirror row
per tool call. The default database lives at ``$NOUS_HOME/state.db`` and is
opened with WAL so reads and writes do not block each other.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel

__all__ = ["AuditEntry", "StateTransition", "init_db", "make_engine"]


class StateTransition(SQLModel, table=True):
    __tablename__ = "state_transitions"

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    from_mode: str
    to_mode: str
    trigger: str
    reason: str = ""


class AuditEntry(SQLModel, table=True):
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
