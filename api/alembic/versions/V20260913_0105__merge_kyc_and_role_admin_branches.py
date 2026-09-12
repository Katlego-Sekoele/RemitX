"""merge kyc and role-admin branches

Role administration (#84) and the KYC lifecycle (#85) each hung a chain off
`drop_users_role` (916c56a3b1f9). Merging them without this revision leaves
two heads, and `alembic upgrade head` fails with "Multiple head revisions
are present".

This rejoins them. No schema change — a merge point only reconnects the graph.

Revision ID: a71e4c90b2d3
Revises: 0c9b5e24af71, 3c8a1e6b5d72
Create Date: 2026-09-13 00:05:00.000000+00:00

"""

# revision identifiers, used by Alembic.
revision: str = "a71e4c90b2d3"
down_revision: str | None = ("0c9b5e24af71", "3c8a1e6b5d72")
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
