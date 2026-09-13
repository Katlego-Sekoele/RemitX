"""create kyc risk rule tables

The risk rule set as rows: `kyc_risk_ratings` (score bands and what each
rating means — max tier, limit percentage, review interval, senior approval)
and `kyc_risk_signals` (what each signal adds to the 0-100 score, and whether
it is evaluated at all). Seeded with the starting rule set; tuned by UPDATE
afterwards, with no release.

`kyc_applications.risk_rating` swaps the CHECK built from the old Python enum
for a foreign key to `kyc_risk_ratings`, so the catalogue is the one list of
valid ratings. Nothing writes the column yet, so the swap is safe against the
app version already running (alembic/README.md rule 5).

Revision ID: e2b5f8c31d62
Revises: d1a4e7b20c51
Create Date: 2026-09-13 10:05:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.kyc_seed import RISK_RATING_SEEDS, RISK_SIGNAL_SEEDS

revision: str = "e2b5f8c31d62"
down_revision: str | None = "d1a4e7b20c51"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "kyc_risk_ratings",
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("min_score", sa.SmallInteger(), nullable=False),
        sa.Column("max_score", sa.SmallInteger(), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("max_tier", sa.SmallInteger(), nullable=False),
        sa.Column("limit_percent", sa.SmallInteger(), nullable=False),
        sa.Column("review_interval_days", sa.Integer(), nullable=False),
        sa.Column("requires_senior_approval", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "min_score >= 0 AND max_score <= 100 AND min_score <= max_score",
            name="kyc_risk_ratings_score_band_valid",
        ),
        sa.CheckConstraint(
            "max_tier >= 1",
            name="kyc_risk_ratings_max_tier_allows_approval",
        ),
        sa.CheckConstraint(
            "limit_percent > 0 AND limit_percent <= 100",
            name="kyc_risk_ratings_limit_percent_valid",
        ),
        sa.CheckConstraint(
            "review_interval_days > 0",
            name="kyc_risk_ratings_review_interval_positive",
        ),
        sa.ForeignKeyConstraint(
            ["max_tier"],
            ["kyc_tiers.tier"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("rating"),
        sa.UniqueConstraint("severity"),
    )
    op.create_table(
        "kyc_risk_signals",
        sa.Column("signal", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("score_effect", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "score_effect >= 0 AND score_effect <= 100",
            name="kyc_risk_signals_score_effect_in_range",
        ),
        sa.PrimaryKeyConstraint("signal"),
    )

    ratings = sa.table(
        "kyc_risk_ratings",
        sa.column("rating", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("min_score", sa.SmallInteger()),
        sa.column("max_score", sa.SmallInteger()),
        sa.column("severity", sa.SmallInteger()),
        sa.column("max_tier", sa.SmallInteger()),
        sa.column("limit_percent", sa.SmallInteger()),
        sa.column("review_interval_days", sa.Integer()),
        sa.column("requires_senior_approval", sa.Boolean()),
    )
    op.bulk_insert(
        ratings,
        [
            {
                "rating": seed.rating,
                "description": seed.description,
                "min_score": seed.min_score,
                "max_score": seed.max_score,
                "severity": seed.severity,
                "max_tier": seed.max_tier,
                "limit_percent": seed.limit_percent,
                "review_interval_days": seed.review_interval_days,
                "requires_senior_approval": seed.requires_senior_approval,
            }
            for seed in RISK_RATING_SEEDS
        ],
    )

    signals = sa.table(
        "kyc_risk_signals",
        sa.column("signal", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("score_effect", sa.SmallInteger()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        signals,
        [
            {
                "signal": seed.signal,
                "description": seed.description,
                "score_effect": seed.score_effect,
                "is_active": True,
            }
            for seed in RISK_SIGNAL_SEEDS
        ],
    )

    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_constraint("kyc_applications_risk_rating_valid", type_="check")
        batch_op.create_foreign_key(
            "kyc_applications_risk_rating_fkey",
            "kyc_risk_ratings",
            ["risk_rating"],
            ["rating"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_constraint(
            "kyc_applications_risk_rating_fkey", type_="foreignkey"
        )
        batch_op.create_check_constraint(
            "kyc_applications_risk_rating_valid",
            "risk_rating IS NULL OR risk_rating IN ('low', 'medium', 'high')",
        )
    op.drop_table("kyc_risk_signals")
    op.drop_table("kyc_risk_ratings")
