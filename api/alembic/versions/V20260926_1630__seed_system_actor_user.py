"""Seed the system actor user for audit_log entries (issue #54).

Revision ID: c4d5e6f7a8b9
Revises: b3a8c1d4e5f6
Create Date: 2026-09-26 16:30:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3a8c1d4e5f6"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_SYSTEM_ID = "00000000-0000-4000-8000-000000000002"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO users (
                id,
                clerk_user_id,
                email,
                first_name,
                base_reference
            )
            VALUES (
                :id,
                'user_remitx_system',
                'system@internal.remitx',
                'System',
                'system1'
            )
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(id=_SYSTEM_ID)
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM users WHERE id = :id").bindparams(id=_SYSTEM_ID)
    )
