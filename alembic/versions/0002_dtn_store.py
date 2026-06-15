"""dtn store: dtn_bundles, dtn_meta (BL-056 increment 4).

Revision ID: 0002_dtn_store
Revises: 0001_baseline
Create Date: 2026-06-15

Mirrors ``nous.db.DtnBundleRow`` and ``nous.db.DtnMetaRow``: the persisted DTN
mesh store (ADR 0064). ``init_db`` still creates these idempotently via
``SQLModel.metadata.create_all`` on first boot, so the upgrade skips any table
that already exists, the same retroactive-adoption pattern as the baseline.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_dtn_store"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the DTN store schema, skipping any table already present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "dtn_bundles" not in existing_tables:
        op.create_table(
            "dtn_bundles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("holder_eid", sa.String(), nullable=False),
            sa.Column("bundle_id", sa.String(), nullable=False),
            sa.Column("source_eid", sa.String(), nullable=False),
            sa.Column("dest_eid", sa.String(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("precedence", sa.String(), nullable=False),
            sa.Column("created_ts_s", sa.Float(), nullable=False),
            sa.Column("expiry_ts_s", sa.Float(), nullable=True),
            sa.Column(
                "custody", sa.Boolean(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("hops", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
        )

    if "dtn_meta" not in existing_tables:
        op.create_table(
            "dtn_meta",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ts_s", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "next_seq", sa.Integer(), nullable=False, server_default=sa.text("1")
            ),
            sa.Column(
                "originated", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "delivered", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "forwarded", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "retransmits", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "dropped", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "expired", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "deduped", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "delivered_ids", sa.String(), nullable=False, server_default=""
            ),
            sa.Column("node_seen", sa.String(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "dtn_meta" in existing_tables:
        op.drop_table("dtn_meta")
    if "dtn_bundles" in existing_tables:
        op.drop_table("dtn_bundles")
