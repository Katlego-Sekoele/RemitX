"""merge users-profile branches

The user-profile chain (last_name/mobile_number/country,
393879e988d7) and the KYC-RLS chain (mobile_number only,
63c9656baaa8) were combined in git (main merged into remittance-quotes)
but never reconciled as Alembic heads — `alembic upgrade head` fails
with "Multiple head revisions" until this lands. The KYC-RLS chain's own
`mobile_number` add was emptied out in 63c9656baaa8 itself (its own file),
since the other chain already adds that column — otherwise this merge
would replay both and fail on Postgres with "column already exists".

Revision ID: f35202d9c724
Revises: 393879e988d7, 63c9656baaa8
Create Date: 2026-09-20 12:00:00.000000+00:00

"""

# revision identifiers, used by Alembic.
revision: str = "f35202d9c724"
down_revision: str | None = ("393879e988d7", "63c9656baaa8")
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
