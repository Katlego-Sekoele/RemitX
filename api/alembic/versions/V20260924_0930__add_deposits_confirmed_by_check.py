"""add deposits confirmed_by check

``confirmed_by`` is either unset, the literal ``system`` for automatic
matching, or a staff user id (UUID text) once an admin confirms a line.

Revision ID: c4b8e2f1a903
Revises: a7c3e91b4d20
Create Date: 2026-09-24 09:30:00.000000+00:00

"""

from alembic import op

revision: str = "c4b8e2f1a903"
down_revision: str | None = "a7c3e91b4d20"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_CHECK = (
    "confirmed_by IS NULL OR confirmed_by = 'system' OR "
    "(length(confirmed_by) = 36 AND substr(confirmed_by, 9, 1) = '-' "
    "AND substr(confirmed_by, 14, 1) = '-' AND substr(confirmed_by, 19, 1) = '-' "
    "AND substr(confirmed_by, 24, 1) = '-')"
)


def upgrade() -> None:
    op.create_check_constraint(
        "deposits_confirmed_by_actor",
        "deposits",
        _CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("deposits_confirmed_by_actor", "deposits", type_="check")
