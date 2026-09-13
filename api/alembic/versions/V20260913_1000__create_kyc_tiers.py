"""create kyc tiers

The verification tier ladder and each tier's daily and monthly limits, as
configuration rather than constants in the limits path. Seeded with the
brief's figures for tiers 0 and 1 and ours for tier 2.

`kyc_applications.tier_granted` gains a foreign key, so an approval cannot
grant a tier this table does not define. Every value the running code writes
(1) is seeded first, so it is safe against the app version already running
(alembic/README.md rule 5).

Revision ID: d1a4e7b20c51
Revises: c7f2a91e4b18
Create Date: 2026-09-13 10:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.kyc_seed import TIER_SEEDS

revision: str = "d1a4e7b20c51"
down_revision: str | None = "c7f2a91e4b18"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "kyc_tiers",
        sa.Column("tier", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("daily_limit_zar", sa.Numeric(18, 2), nullable=False),
        sa.Column("monthly_limit_zar", sa.Numeric(18, 2), nullable=False),
        sa.Column("requires_source_of_wealth", sa.Boolean(), nullable=False),
        sa.CheckConstraint("tier >= 0", name="kyc_tiers_tier_non_negative"),
        sa.CheckConstraint(
            "daily_limit_zar >= 0 AND monthly_limit_zar >= daily_limit_zar",
            name="kyc_tiers_limits_valid",
        ),
        sa.PrimaryKeyConstraint("tier"),
    )

    tiers = sa.table(
        "kyc_tiers",
        sa.column("tier", sa.SmallInteger()),
        sa.column("name", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("daily_limit_zar", sa.Numeric(18, 2)),
        sa.column("monthly_limit_zar", sa.Numeric(18, 2)),
        sa.column("requires_source_of_wealth", sa.Boolean()),
    )
    op.bulk_insert(
        tiers,
        [
            {
                "tier": seed.tier,
                "name": seed.name,
                "description": seed.description,
                "daily_limit_zar": seed.daily_limit_zar,
                "monthly_limit_zar": seed.monthly_limit_zar,
                "requires_source_of_wealth": seed.requires_source_of_wealth,
            }
            for seed in TIER_SEEDS
        ],
    )

    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.create_foreign_key(
            "kyc_applications_tier_granted_fkey",
            "kyc_tiers",
            ["tier_granted"],
            ["tier"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_constraint(
            "kyc_applications_tier_granted_fkey", type_="foreignkey"
        )
    op.drop_table("kyc_tiers")
