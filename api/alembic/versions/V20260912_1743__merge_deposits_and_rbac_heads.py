"""merge deposits and rbac heads

The deposits chain (accounts/transactions/deposits) and the rbac/user-profile
merge chain were combined in git (deposits PR merged into main after the rbac
merge already landed) but never reconciled as Alembic heads — `alembic
upgrade head` fails with "Multiple head revisions" until this lands.

Revision ID: eeb69031af57
Revises: f28d4a6e9c13, 57b763cacca1
Create Date: 2026-09-12 17:43:00.000000+00:00

"""

# revision identifiers, used by Alembic.
revision: str = "eeb69031af57"
down_revision: str | None = ("f28d4a6e9c13", "57b763cacca1")
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
