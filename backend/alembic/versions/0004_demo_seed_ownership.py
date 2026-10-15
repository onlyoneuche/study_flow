"""Record demo seed ownership without weakening immutable ledger history.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op
from app.db.types import UTCDateTime

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_seed_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at", UTCDateTime(), server_default=sa.func.current_timestamp(), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("user_ids", sa.JSON(), nullable=False),
        sa.Column("group_ids", sa.JSON(), nullable=False),
        sa.Column("archived_at", UTCDateTime(), nullable=True),
    )
    op.create_index(
        "uq_demo_seed_active",
        "demo_seed_runs",
        ["is_active"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade():
    op.drop_table("demo_seed_runs")
