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

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, desc, event
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, select

__all__ = [
    "AuditEntry",
    "DtnBundleRow",
    "DtnMetaRow",
    "DtnStore",
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


class DtnBundleRow(SQLModel, table=True):
    """A persisted in-flight DTN bundle (BL-056 increment 4, ADR 0064).

    One row per bundle held in a node's store at the last checkpoint. The holder
    node EID owns the row; the bundle state is implicitly ``in_transit``
    (delivered, dropped, and expired bundles are not held, so are not persisted).
    """

    __tablename__ = "dtn_bundles"

    id: int | None = Field(default=None, primary_key=True)
    holder_eid: str
    bundle_id: str
    source_eid: str
    dest_eid: str
    sequence: int
    size_bytes: int
    precedence: str
    created_ts_s: float
    expiry_ts_s: float | None = None
    custody: bool = False
    hops: int = 0
    attempts: int = 0


class DtnMetaRow(SQLModel, table=True):
    """The single-row DTN mesh bookkeeping snapshot (BL-056 increment 4).

    Holds what the bundle rows do not: the snapshot's simulated time (for
    lifetime rebasing on restore across a clock reset), the next origination
    sequence, the disposition counters, and the bounded dedup ledgers (the
    mesh-wide delivered-id list and the per-node seen lists, JSON-encoded).
    """

    __tablename__ = "dtn_meta"

    id: int | None = Field(default=None, primary_key=True)
    ts_s: float = 0.0
    next_seq: int = 1
    originated: int = 0
    delivered: int = 0
    forwarded: int = 0
    retransmits: int = 0
    dropped: int = 0
    expired: int = 0
    deduped: int = 0
    delivered_ids: str = ""
    node_seen: str = ""


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

    A ``None`` engine has two meanings the caller must distinguish: the
    intentional memory-only mode (the pure-Python engine constructs
    ``StateTransitionLog(None)`` and persists nothing by design), and a
    failed ``init_db`` at server start (``server.py`` swallows the error
    so the engine still ticks). The optional ``init_error`` separates
    them: an empty string is the intentional mode, a non-empty string
    means persistence was configured but failed to come up. :meth:`status`
    and :attr:`degraded` surface that distinction so ``device_info`` can
    report a silently unpersisted transition history (AUDIT-2026-06-14
    DB-1) instead of leaving an operator to discover it from an empty
    ``state_history``.

    ``init_error`` and ``last_error`` carry only the exception *class*, not
    the message: ``device_info`` is a T0 read any caller can reach, and a
    connection-time exception message can include the DB URL and its
    credentials (a Postgres/MySQL ``NOUS_DB_URL``). The full message is
    written to stderr at the point of failure for an operator with host
    access.
    """

    def __init__(self, engine: Engine | None, *, init_error: str = "") -> None:
        self.engine = engine
        self.init_error = init_error
        self.append_failures = 0
        self.last_error = ""

    @property
    def degraded(self) -> bool:
        """True when persistence is configured but not working.

        A ``None`` engine with no ``init_error`` is the intentional
        memory-only mode, not a degradation. A ``None`` engine with an
        ``init_error`` means ``init_db`` failed at start; a live engine
        with append failures means a runtime write fault.
        """
        if self.engine is None:
            return bool(self.init_error)
        return self.append_failures > 0

    def status(self) -> dict[str, Any]:
        """Read-only persistence health for ``device_info``."""
        return {
            "persistent": self.engine is not None,
            "degraded": self.degraded,
            "init_error": self.init_error,
            "append_failures": self.append_failures,
            "last_error": self.last_error,
        }

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
            self.last_error = exc.__class__.__name__

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
            self.last_error = exc.__class__.__name__
            return []


_DTN_COUNTER_KEYS = (
    "originated",
    "delivered",
    "forwarded",
    "retransmits",
    "dropped",
    "expired",
    "deduped",
)


class DtnStore:
    """Persist and restore the DTN mesh store across a restart (ADR 0064).

    The engine checkpoints the mesh after a mutating tick and restores it when a
    fresh ``DtnMesh`` is built (a process restart or a hot reload), so in-flight
    and in-custody bundles survive a node restart, not just a link drop. Writes
    are best effort and degrade silently like :class:`StateTransitionLog`: a
    flaky DB cannot stall the tick loop. A ``None`` engine is the intentional
    memory-only mode (nothing persists); a non-empty ``init_error`` flags a
    configured-but-failed DB. Only the exception *class* is retained, never the
    message, so a DB URL with credentials cannot leak through the ``dtn_mesh``
    read.
    """

    def __init__(self, engine: Engine | None, *, init_error: str = "") -> None:
        self.engine = engine
        self.init_error = init_error
        self.save_failures = 0
        self.last_error = ""
        self.load_failures = 0
        self.last_load_error = ""

    @property
    def degraded(self) -> bool:
        if self.engine is None:
            return bool(self.init_error)
        return self.save_failures > 0 or self.load_failures > 0

    def status(self) -> dict[str, Any]:
        """Read-only DTN persistence health for the ``dtn_mesh`` read."""
        return {
            "persistent": self.engine is not None,
            "degraded": self.degraded,
            "init_error": self.init_error,
            "save_failures": self.save_failures,
            "last_error": self.last_error,
            "load_failures": self.load_failures,
            "last_load_error": self.last_load_error,
        }

    def save(self, snapshot: Mapping[str, Any]) -> None:
        """Replace the persisted store with ``snapshot`` in one transaction."""
        if self.engine is None:
            return
        counters: Mapping[str, Any] = snapshot.get("counters", {})
        nodes: Mapping[str, Any] = snapshot.get("nodes", {})
        try:
            with Session(self.engine) as session:
                for bundle_row in session.exec(select(DtnBundleRow)).all():
                    session.delete(bundle_row)
                for meta_row in session.exec(select(DtnMetaRow)).all():
                    session.delete(meta_row)
                session.add(
                    DtnMetaRow(
                        id=1,
                        ts_s=float(snapshot.get("ts_s", 0.0)),
                        next_seq=int(snapshot.get("next_seq", 1)),
                        originated=int(counters.get("originated", 0)),
                        delivered=int(counters.get("delivered", 0)),
                        forwarded=int(counters.get("forwarded", 0)),
                        retransmits=int(counters.get("retransmits", 0)),
                        dropped=int(counters.get("dropped", 0)),
                        expired=int(counters.get("expired", 0)),
                        deduped=int(counters.get("deduped", 0)),
                        delivered_ids=json.dumps(list(snapshot.get("delivered_ids", []))),
                        node_seen=json.dumps(
                            {eid: list(n.get("seen", [])) for eid, n in nodes.items()}
                        ),
                    )
                )
                for eid, node in nodes.items():
                    for b in node.get("bundles", []):
                        session.add(
                            DtnBundleRow(
                                holder_eid=eid,
                                bundle_id=b["bundle_id"],
                                source_eid=b["source_eid"],
                                dest_eid=b["dest_eid"],
                                sequence=int(b["sequence"]),
                                size_bytes=int(b["size_bytes"]),
                                precedence=str(b["precedence"]),
                                created_ts_s=float(b["created_ts_s"]),
                                expiry_ts_s=(
                                    None
                                    if b["expiry_ts_s"] is None
                                    else float(b["expiry_ts_s"])
                                ),
                                custody=bool(b["custody"]),
                                hops=int(b["hops"]),
                                attempts=int(b["attempts"]),
                            )
                        )
                session.commit()
        except Exception as exc:  # noqa: BLE001
            self.save_failures += 1
            self.last_error = exc.__class__.__name__

    def load(self) -> dict[str, Any] | None:
        """Return the persisted snapshot, or ``None`` when nothing is stored.

        Best effort: a DB read failure or a corrupt JSON ledger is caught,
        counted as a degradation, and returned as ``None`` rather than raised, so
        a bad store cannot crash engine init or a hot reload.
        """
        if self.engine is None:
            return None
        try:
            with Session(self.engine) as session:
                meta = session.exec(select(DtnMetaRow)).first()
                if meta is None:
                    return None
                bundles = list(session.exec(select(DtnBundleRow)).all())
            seen_map: dict[str, list[str]] = json.loads(meta.node_seen or "{}")
            nodes: dict[str, dict[str, Any]] = {
                eid: {"seen": list(seen), "bundles": []}
                for eid, seen in seen_map.items()
            }
            for row in bundles:
                node = nodes.setdefault(row.holder_eid, {"seen": [], "bundles": []})
                node["bundles"].append(
                    {
                        "bundle_id": row.bundle_id,
                        "source_eid": row.source_eid,
                        "dest_eid": row.dest_eid,
                        "sequence": row.sequence,
                        "size_bytes": row.size_bytes,
                        "precedence": row.precedence,
                        "created_ts_s": row.created_ts_s,
                        "expiry_ts_s": row.expiry_ts_s,
                        "custody": row.custody,
                        "hops": row.hops,
                        "attempts": row.attempts,
                    }
                )
            return {
                "ts_s": meta.ts_s,
                "next_seq": meta.next_seq,
                "counters": {k: getattr(meta, k) for k in _DTN_COUNTER_KEYS},
                "delivered_ids": json.loads(meta.delivered_ids or "[]"),
                "nodes": nodes,
            }
        except Exception as exc:  # noqa: BLE001
            self.load_failures += 1
            self.last_load_error = exc.__class__.__name__
            return None
