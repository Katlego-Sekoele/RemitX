"""seed platform accounts

Inserts RemitX's platform accounts (``platform_account_seed.py``): a bank and
a fee revenue account per settlement country, the XRPL treasury wallet and
the uctusd issuer. They used to be created by
``scripts/seed_platform_accounts.py``; every environment now gets them from
``alembic upgrade head``.

Environments that already ran that script keep their rows, balances and
ledger history. An account is inserted only when no platform account with its
label exists yet, which is the same test the script used.

The downgrade deletes the rows this revision inserted, found by their
deterministic ids. Rows the script created have random ids and stay. A seeded
account that has taken a transaction fails the delete on its foreign key
rather than orphaning ledger history.

Revision ID: 198395894d4a
Revises: 728add2cc9e2
Create Date: 2026-09-24 12:54:08.209563+00:00

"""

from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.platform_account_seed import PLATFORM_ACCOUNT_SEEDS

# revision identifiers, used by Alembic.
revision: str = "198395894d4a"
down_revision: str | None = "728add2cc9e2"
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
        if seed.label not in existing
    ]
    if rows:
        op.bulk_insert(_accounts, rows)


def downgrade() -> None:
    op.execute(
        _accounts.delete().where(
            _accounts.c.account_id.in_(
                [seed.account_id for seed in PLATFORM_ACCOUNT_SEEDS]
            )
        )
    )
