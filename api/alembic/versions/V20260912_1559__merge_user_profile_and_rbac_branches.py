"""merge user profile and rbac branches

Revision ID: 57b763cacca1
Revises: a1c5e08f3d67, c3a91f5e82b1
Create Date: 2026-09-12 15:59:08.404378+00:00

"""

# revision identifiers, used by Alembic.
revision: str = "57b763cacca1"
down_revision: str | None = ("a1c5e08f3d67", "c3a91f5e82b1")
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
