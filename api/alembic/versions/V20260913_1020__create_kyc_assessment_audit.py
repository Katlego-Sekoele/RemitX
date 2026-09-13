"""create kyc assessment audit

Append-only record of every risk rating and tier change on an application —
computed value, final value, and the reason wherever they differ, which a
CHECK enforces. `kyc_assessment_audit_signals` holds the signals that fired
for a scored row with the score effect each carried at the time, so reweighting
a signal later never rewrites an old assessment.

New tables only, so it is safe against the app version already running
(alembic/README.md rule 5).

Revision ID: b5e8c1f64a95
Revises: a4d7b0e53f84
Create Date: 2026-09-13 10:20:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

revision: str = "b5e8c1f64a95"
down_revision: str | None = "a4d7b0e53f84"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "kyc_assessment_audit",
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("computed_risk_rating", sa.Text(), nullable=True),
        sa.Column("final_risk_rating", sa.Text(), nullable=True),
        sa.Column("risk_score", sa.SmallInteger(), nullable=True),
        sa.Column("computed_tier", sa.SmallInteger(), nullable=True),
        sa.Column("final_tier", sa.SmallInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(final_risk_rating IS NULL) <> (final_tier IS NULL)",
            name="kyc_assessment_audit_one_subject",
        ),
        sa.CheckConstraint(
            "reason IS NOT NULL OR ("
            "(final_risk_rating IS NULL OR "
            "(computed_risk_rating IS NOT NULL "
            "AND computed_risk_rating = final_risk_rating)) "
            "AND (final_tier IS NULL OR "
            "(computed_tier IS NOT NULL AND computed_tier = final_tier)))",
            name="kyc_assessment_audit_reason_when_overridden",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["kyc_applications.application_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["computed_risk_rating"],
            ["kyc_risk_ratings.rating"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["final_risk_rating"],
            ["kyc_risk_ratings.rating"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["computed_tier"],
            ["kyc_tiers.tier"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["final_tier"],
            ["kyc_tiers.tier"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index(
        "idx_kyc_assessment_audit_application_recorded_at",
        "kyc_assessment_audit",
        ["application_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_kyc_assessment_audit_application_id"),
        "kyc_assessment_audit",
        ["application_id"],
        unique=False,
    )

    op.create_table(
        "kyc_assessment_audit_signals",
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("signal", sa.Text(), nullable=False),
        sa.Column("score_effect", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["audit_id"],
            ["kyc_assessment_audit.audit_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["signal"],
            ["kyc_risk_signals.signal"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("audit_id", "signal"),
    )


def downgrade() -> None:
    op.drop_table("kyc_assessment_audit_signals")
    op.drop_index(
        op.f("ix_kyc_assessment_audit_application_id"),
        table_name="kyc_assessment_audit",
    )
    op.drop_index(
        "idx_kyc_assessment_audit_application_recorded_at",
        table_name="kyc_assessment_audit",
    )
    op.drop_table("kyc_assessment_audit")
