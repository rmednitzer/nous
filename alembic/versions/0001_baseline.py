"""baseline schema: state_transitions, audit_entries (BL-015).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-26

Mirrors ``nous.db.StateTransition`` and ``nous.db.AuditEntry`` at
the v0.1 schema. ``init_db`` still creates these tables idempotently
on first boot for developer ergonomics; the migration is the
authoritative source once a deployment has crossed the first
schema-evolution boundary (BL-051).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the baseline schema.

    Idempotent: ``nous.db.init_db()`` already creates the same tables
    on first boot via ``SQLModel.metadata.create_all``, so a deployment
    that booted before Alembic was introduced will have the tables
    already present. We check the inspector and skip the
    ``create_table`` calls for any table that already exists, so
    ``alembic upgrade head`` can be adopted retroactively without a
    "table already exists" error. Indexes get the same treatment.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    def _existing_indexes(table: str) -> set[str]:
        if table not in existing_tables:
            return set()
        return {ix["name"] for ix in inspector.get_indexes(table) if ix.get("name")}

    if "state_transitions" not in existing_tables:
        op.create_table(
            "state_transitions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "ts",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("from_mode", sa.String(length=64), nullable=False),
            sa.Column("to_mode", sa.String(length=64), nullable=False),
            sa.Column("trigger", sa.String(length=64), nullable=False),
            sa.Column("reason", sa.String(length=256), nullable=False, server_default=""),
        )
    if "ix_state_transitions_ts" not in _existing_indexes("state_transitions"):
        op.create_index(
            "ix_state_transitions_ts", "state_transitions", ["ts"], unique=False
        )

    if "audit_entries" not in existing_tables:
        op.create_table(
            "audit_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "ts",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("tool", sa.String(length=64), nullable=False),
            sa.Column("tier", sa.Integer(), nullable=False),
            sa.Column(
                "denied",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("output_sha256", sa.String(length=64), nullable=False),
            sa.Column("output_len", sa.Integer(), nullable=False),
            sa.Column("exit_code", sa.Integer(), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("client_id", sa.String(length=64), nullable=False, server_default=""),
        )
    audit_indexes = _existing_indexes("audit_entries")
    if "ix_audit_entries_ts" not in audit_indexes:
        op.create_index("ix_audit_entries_ts", "audit_entries", ["ts"], unique=False)
    if "ix_audit_entries_tool" not in audit_indexes:
        op.create_index(
            "ix_audit_entries_tool", "audit_entries", ["tool"], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "audit_entries" in existing_tables:
        audit_indexes = {
            ix["name"] for ix in inspector.get_indexes("audit_entries") if ix.get("name")
        }
        if "ix_audit_entries_tool" in audit_indexes:
            op.drop_index("ix_audit_entries_tool", table_name="audit_entries")
        if "ix_audit_entries_ts" in audit_indexes:
            op.drop_index("ix_audit_entries_ts", table_name="audit_entries")
        op.drop_table("audit_entries")
    if "state_transitions" in existing_tables:
        st_indexes = {
            ix["name"]
            for ix in inspector.get_indexes("state_transitions")
            if ix.get("name")
        }
        if "ix_state_transitions_ts" in st_indexes:
            op.drop_index("ix_state_transitions_ts", table_name="state_transitions")
        op.drop_table("state_transitions")
