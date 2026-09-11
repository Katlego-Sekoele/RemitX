"""drop redundant roles name unique constraint

The RBAC create migration declared both ``roles_name_key`` and
``ix_roles_name``. The ORM only models the unique index, so drop the extra
constraint when present.

Revision ID: b7e2d4f81a06
Revises: a4f8c2e91d03
Create Date: 2026-09-12 01:30:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2d4f81a06"
down_revision: str | None = "a4f8c2e91d03"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_name_key"))


def downgrade() -> None:
    op.create_unique_constraint("roles_name_key", "roles", ["name"])
