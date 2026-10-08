"""allow eur gbp bwp lsl mwk mzn payout currency

EUR, GBP, BWP, LSL, MWK and MZN join ZAR, USD, ZWL and NAD as valid
beneficiary payout currencies.

Revision ID: b056ec2e1eef
Revises: 2a81c1c47289
Create Date: 2026-09-27 18:10:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b056ec2e1eef"
down_revision: str | None = "2a81c1c47289"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_CONSTRAINT = "beneficiaries_payout_currency_valid"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "beneficiaries", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "beneficiaries",
        "payout_currency IN ('ZAR', 'USD', 'ZWL', 'NAD', 'EUR', 'GBP', 'BWP', "
        "'LSL', 'MWK', 'MZN')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "beneficiaries", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "beneficiaries",
        "payout_currency IN ('ZAR', 'USD', 'ZWL', 'NAD')",
    )
