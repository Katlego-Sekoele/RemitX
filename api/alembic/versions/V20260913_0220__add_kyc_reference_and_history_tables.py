"""add kyc reference and history tables

Revision ID: b4e8c1d29f03
Revises: a71e4c90b2d3
Create Date: 2026-09-13 02:20:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.kyc_lifecycle import APPLICATION_STATUSES, sql_value_list
from remitx_api.models.orm.kyc_seed import (
    PROGRESSION_SEEDS,
    REASON_CODE_SEEDS,
    precompute_progression_id,
)

revision: str = "b4e8c1d29f03"
down_revision: str | None = "a71e4c90b2d3"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_APPLICATION_STATUSES = sql_value_list(APPLICATION_STATUSES)


def upgrade() -> None:
    op.create_table(
        "kyc_reason_codes",
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("reason_code"),
    )
    op.create_table(
        "kyc_status_progressions",
        sa.Column("progression_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=False),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.CheckConstraint(
            f"from_status IN ({_APPLICATION_STATUSES})",
            name="kyc_status_progressions_from_status_valid",
        ),
        sa.CheckConstraint(
            f"to_status IN ({_APPLICATION_STATUSES})",
            name="kyc_status_progressions_to_status_valid",
        ),
        sa.PrimaryKeyConstraint("progression_id"),
        sa.UniqueConstraint(
            "from_status",
            "to_status",
            name="uq_kyc_status_progressions_from_to",
        ),
    )
    op.create_table(
        "kyc_decision_history",
        sa.Column("history_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("made_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("made_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_APPLICATION_STATUSES})",
            name="kyc_decision_history_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["kyc_applications.application_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["made_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reason_code"],
            ["kyc_reason_codes.reason_code"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("history_id"),
    )
    op.create_index(
        "idx_kyc_decision_history_application_made_at",
        "kyc_decision_history",
        ["application_id", "made_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_kyc_decision_history_application_id"),
        "kyc_decision_history",
        ["application_id"],
        unique=False,
    )

    reason_codes = sa.table(
        "kyc_reason_codes",
        sa.column("reason_code", sa.Text()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        reason_codes,
        [
            {"reason_code": seed.code.value, "description": seed.description}
            for seed in REASON_CODE_SEEDS
        ],
    )

    progressions = sa.table(
        "kyc_status_progressions",
        sa.column("progression_id", sa.Uuid()),
        sa.column("from_status", sa.Text()),
        sa.column("to_status", sa.Text()),
    )
    op.bulk_insert(
        progressions,
        [
            {
                "progression_id": precompute_progression_id(
                    seed.from_status.value,
                    seed.to_status.value,
                ),
                "from_status": seed.from_status.value,
                "to_status": seed.to_status.value,
            }
            for seed in PROGRESSION_SEEDS
        ],
    )

    with op.batch_alter_table("kyc_decisions") as batch_op:
        batch_op.drop_constraint("kyc_decisions_reason_code_valid", type_="check")
        batch_op.create_foreign_key(
            "kyc_decisions_reason_code_fkey",
            "kyc_reason_codes",
            ["reason_code"],
            ["reason_code"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("kyc_decisions") as batch_op:
        batch_op.drop_constraint("kyc_decisions_reason_code_fkey", type_="foreignkey")
        batch_op.create_check_constraint(
            "kyc_decisions_reason_code_valid",
            "reason_code IS NULL OR reason_code IN ('identity_verified', "
            "'document_illegible', 'document_expired', 'document_missing', "
            "'details_mismatch', 'sanctions_match', 'suspected_fraud', "
            "'unsupported_jurisdiction', 'under_age', 'other')",
        )

    op.drop_index(
        op.f("ix_kyc_decision_history_application_id"),
        table_name="kyc_decision_history",
    )
    op.drop_index(
        "idx_kyc_decision_history_application_made_at",
        table_name="kyc_decision_history",
    )
    op.drop_table("kyc_decision_history")
    op.drop_table("kyc_status_progressions")
    op.drop_table("kyc_reason_codes")
