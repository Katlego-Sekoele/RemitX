"""merge kyc-risk and kyc-document branches

KYC document upload (on main) and KYC risk scoring (#88) each hung a chain
off `add_kyc_application_status_and_history` (c7f2a91e4b18). Merging them
without this revision leaves two heads, and `alembic upgrade head` fails
with "Multiple head revisions are present".

This rejoins them. No schema change — a merge point only reconnects the graph.

Revision ID: bc1240f4d035
Revises: e9c14b2a7f36, c6f9d2a75b06
Create Date: 2026-09-13 01:10:00.000000+00:00

"""

# revision identifiers, used by Alembic.
revision: str = "bc1240f4d035"
down_revision: str | None = ("e9c14b2a7f36", "c6f9d2a75b06")
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
