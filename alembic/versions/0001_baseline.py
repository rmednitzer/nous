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
    op.create_index(
        "ix_state_transitions_ts", "state_transitions", ["ts"], unique=False
    )

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
    op.create_index("ix_audit_entries_ts", "audit_entries", ["ts"], unique=False)
    op.create_index(
        "ix_audit_entries_tool", "audit_entries", ["tool"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_entries_tool", table_name="audit_entries")
    op.drop_index("ix_audit_entries_ts", table_name="audit_entries")
    op.drop_table("audit_entries")
    op.drop_index("ix_state_transitions_ts", table_name="state_transitions")
    op.drop_table("state_transitions")
