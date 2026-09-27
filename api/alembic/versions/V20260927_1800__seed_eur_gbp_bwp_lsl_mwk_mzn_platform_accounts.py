"""seed eur gbp bwp lsl mwk mzn platform accounts

Opens six new settlement countries (``platform_account_seed.py``): EUR, GBP,
BWP, LSL, MWK and MZN, each getting a bank account and a fee revenue account,
mirroring ``V20260924_1254__seed_platform_accounts.py``. Only rows not
already present (matched by label) are inserted, so this is safe to run on an
environment that already has the original four countries seeded.

Revision ID: 2a81c1c47289
Revises: a8c3e1f42b90
Create Date: 2026-09-27 18:00:00.000000+00:00

"""

from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.platform_account_seed import PLATFORM_ACCOUNT_SEEDS

# revision identifiers, used by Alembic.
revision: str = "2a81c1c47289"
down_revision: str | None = "a8c3e1f42b90"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_accounts = sa.table(
    "accounts",
    sa.column("account_id", sa.Uuid()),
    sa.column("user_id", sa.Uuid()),
    sa.column("type", sa.Text()),
    sa.column("reference", sa.Text()),
    sa.column("label", sa.Text()),
    sa.column("account_currency", sa.Text()),
    sa.column("account_balance", sa.Numeric(20, 8)),
    sa.column("created_at", sa.DateTime(timezone=True)),
)

_NEW_LABELS = {
    "RemitX EU Bank Account",
    "RemitX UK Bank Account",
    "RemitX BW Bank Account",
    "RemitX LES Bank Account",
    "RemitX MAL Bank Account",
    "RemitX MOZ Bank Account",
    "RemitX EU Fee Revenue",
    "RemitX UK Fee Revenue",
    "RemitX BW Fee Revenue",
    "RemitX LES Fee Revenue",
    "RemitX MAL Fee Revenue",
    "RemitX MOZ Fee Revenue",
}


def upgrade() -> None:
    existing = set(
        op.get_bind().scalars(
            sa.select(_accounts.c.label).where(_accounts.c.type != "USER")
        )
    )
    seeded_at = datetime.now(UTC)
    rows = [
        {
            "account_id": seed.account_id,
            "user_id": None,
            "type": seed.type,
            "reference": None,
            "label": seed.label,
            "account_currency": seed.currency,
            "account_balance": Decimal("0"),
            "created_at": seeded_at,
        }
        for seed in PLATFORM_ACCOUNT_SEEDS
        if seed.label in _NEW_LABELS and seed.label not in existing
    ]
    if rows:
        op.bulk_insert(_accounts, rows)


def downgrade() -> None:
    op.execute(
        _accounts.delete().where(
            _accounts.c.account_id.in_(
                [
                    seed.account_id
                    for seed in PLATFORM_ACCOUNT_SEEDS
                    if seed.label in _NEW_LABELS
                ]
            )
        )
    )
