"""Tie ledger users to their unique user/session participation.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TRIGGER ledger_participant_user BEFORE INSERT ON points_ledger
        WHEN NEW.user_id != (SELECT user_id FROM session_participants WHERE id = NEW.participant_id)
        BEGIN SELECT RAISE(ABORT, 'ledger user must match participant'); END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER ledger_participant_user")
