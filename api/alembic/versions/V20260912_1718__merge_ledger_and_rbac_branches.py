"""merge ledger and rbac branches

`add_user_profile_fields` (a1c5e08f3d67) was left a branchpoint: the ledger
chain (accounts -> transactions -> deposits) hangs off it, and so does the
earlier merge of the user-profile and RBAC branches. That merge only rejoined
the RBAC branch, so `f28d4a6e9c13` and `57b763cacca1` were both left as heads
and `alembic upgrade head` failed with "Multiple head revisions are present".

This rejoins them. No schema change — a merge point only reconnects the graph.

Revision ID: 12cc69b78b1b
Revises: f28d4a6e9c13, 57b763cacca1
Create Date: 2026-09-12 17:18:15.025657+00:00

"""

# revision identifiers, used by Alembic.
revision: str = "12cc69b78b1b"
down_revision: str | None = ("f28d4a6e9c13", "57b763cacca1")
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
