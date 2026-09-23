"""allow zar payout currency

ZAR is a payout currency. Signup already creates that account, so a sender
can pay someone who has only ever held ZAR.

Revision ID: c4a91e2b7d08
Revises: 5b9e3c7d1f20
Create Date: 2026-09-23 00:15:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a91e2b7d08"
down_revision: str | None = "5b9e3c7d1f20"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_CONSTRAINT = "beneficiaries_payout_currency_valid"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "beneficiaries", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "beneficiaries",
        "payout_currency IN ('ZAR', 'USD', 'ZWL', 'NAD')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "beneficiaries", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "beneficiaries",
        "payout_currency IN ('USD', 'ZWL', 'NAD')",
    )
