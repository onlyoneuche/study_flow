"""Archived ownership must not lock a former member's current audience band.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def install_guard(active_only):
    op.execute("DROP TRIGGER user_level_band")
    active = "g.is_active = 1 AND" if active_only else ""
    op.execute(f"""
        CREATE TRIGGER user_level_band BEFORE UPDATE OF level ON users
        WHEN EXISTS (
            SELECT 1 FROM groups g WHERE {active}
              (g.owner_id = NEW.id OR EXISTS (
                SELECT 1 FROM group_members m WHERE m.group_id = g.id
                AND m.user_id = NEW.id AND m.left_at IS NULL))
              AND g.audience_band != CASE
                WHEN NEW.level IN ('JSS1', 'JSS2', 'JSS3', 'SS1', 'SS2', 'SS3')
                THEN 'secondary' ELSE 'tertiary' END
        )
        BEGIN SELECT RAISE(ABORT, 'level change would create a cross-band group'); END
    """)


def upgrade():
    install_guard(True)


def downgrade():
    install_guard(False)
