"""add kyc application status catalogue and application history

Revision ID: c7f2a91e4b18
Revises: b4e8c1d29f03
Create Date: 2026-09-13 03:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.kyc_seed import (
    APPLICATION_STATUS_SEEDS,
)

revision: str = "c7f2a91e4b18"
down_revision: str | None = "b4e8c1d29f03"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "kyc_application_statuses",
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("is_terminal", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("status"),
    )

    statuses = sa.table(
        "kyc_application_statuses",
        sa.column("status", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("is_open", sa.Boolean()),
        sa.column("is_terminal", sa.Boolean()),
    )
    op.bulk_insert(
        statuses,
        [
            {
                "status": seed.status.value,
                "description": seed.description,
                "is_open": seed.is_open,
                "is_terminal": seed.is_terminal,
            }
            for seed in APPLICATION_STATUS_SEEDS
        ],
    )

    op.rename_table("kyc_status_progressions", "kyc_application_status_progressions")

    with op.batch_alter_table("kyc_application_status_progressions") as batch_op:
        batch_op.drop_constraint(
            "kyc_status_progressions_from_status_valid", type_="check"
        )
        batch_op.drop_constraint(
            "kyc_status_progressions_to_status_valid", type_="check"
        )
        batch_op.drop_constraint("uq_kyc_status_progressions_from_to", type_="unique")
        batch_op.create_unique_constraint(
            "uq_kyc_application_status_progressions_from_to",
            ["from_status", "to_status"],
        )
        batch_op.create_foreign_key(
            "kyc_application_status_progressions_from_status_fkey",
            "kyc_application_statuses",
            ["from_status"],
            ["status"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "kyc_application_status_progressions_to_status_fkey",
            "kyc_application_statuses",
            ["to_status"],
            ["status"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "kyc_application_history",
        sa.Column("history_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("risk_rating", sa.Text(), nullable=True),
        sa.Column("tier_granted", sa.SmallInteger(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["kyc_applications.application_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reason_code"],
            ["kyc_reason_codes.reason_code"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["status"],
            ["kyc_application_statuses.status"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("history_id"),
    )
    op.create_index(
        "idx_kyc_application_history_application_changed_at",
        "kyc_application_history",
        ["application_id", "changed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_kyc_application_history_application_id"),
        "kyc_application_history",
        ["application_id"],
        unique=False,
    )

    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_constraint("kyc_applications_status_valid", type_="check")
        batch_op.create_foreign_key(
            "kyc_applications_status_fkey",
            "kyc_application_statuses",
            ["status"],
            ["status"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("kyc_decision_history") as batch_op:
        batch_op.drop_constraint("kyc_decision_history_status_valid", type_="check")
        batch_op.create_foreign_key(
            "kyc_decision_history_status_fkey",
            "kyc_application_statuses",
            ["status"],
            ["status"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("kyc_decisions") as batch_op:
        batch_op.drop_constraint("kyc_decisions_decision_valid", type_="check")
        batch_op.drop_constraint("kyc_decisions_from_status_valid", type_="check")
        batch_op.create_foreign_key(
            "kyc_decisions_decision_fkey",
            "kyc_application_statuses",
            ["decision"],
            ["status"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "kyc_decisions_from_status_fkey",
            "kyc_application_statuses",
            ["from_status"],
            ["status"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("kyc_decisions") as batch_op:
        batch_op.drop_constraint("kyc_decisions_from_status_fkey", type_="foreignkey")
        batch_op.drop_constraint("kyc_decisions_decision_fkey", type_="foreignkey")
        batch_op.create_check_constraint(
            "kyc_decisions_from_status_valid",
            "from_status IN ('in_progress', 'submitted', 'under_review', "
            "'more_info_required', 'approved', 'rejected', 'review_due')",
        )
        batch_op.create_check_constraint(
            "kyc_decisions_decision_valid",
            "decision IN ('under_review', 'more_info_required', 'approved', "
            "'rejected')",
        )

    with op.batch_alter_table("kyc_decision_history") as batch_op:
        batch_op.drop_constraint("kyc_decision_history_status_fkey", type_="foreignkey")
        batch_op.create_check_constraint(
            "kyc_decision_history_status_valid",
            "status IN ('in_progress', 'submitted', 'under_review', "
            "'more_info_required', 'approved', 'rejected', 'review_due')",
        )

    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_constraint("kyc_applications_status_fkey", type_="foreignkey")
        batch_op.create_check_constraint(
            "kyc_applications_status_valid",
            "status IN ('in_progress', 'submitted', 'under_review', "
            "'more_info_required', 'approved', 'rejected', 'review_due')",
        )

    op.drop_index(
        op.f("ix_kyc_application_history_application_id"),
        table_name="kyc_application_history",
    )
    op.drop_index(
        "idx_kyc_application_history_application_changed_at",
        table_name="kyc_application_history",
    )
    op.drop_table("kyc_application_history")

    with op.batch_alter_table("kyc_application_status_progressions") as batch_op:
        batch_op.drop_constraint(
            "kyc_application_status_progressions_to_status_fkey", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "kyc_application_status_progressions_from_status_fkey", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "uq_kyc_application_status_progressions_from_to", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_kyc_status_progressions_from_to",
            ["from_status", "to_status"],
        )
        batch_op.create_check_constraint(
            "kyc_status_progressions_to_status_valid",
            "to_status IN ('in_progress', 'submitted', 'under_review', "
            "'more_info_required', 'approved', 'rejected', 'review_due')",
        )
        batch_op.create_check_constraint(
            "kyc_status_progressions_from_status_valid",
            "from_status IN ('in_progress', 'submitted', 'under_review', "
            "'more_info_required', 'approved', 'rejected', 'review_due')",
        )

    op.rename_table("kyc_application_status_progressions", "kyc_status_progressions")
    op.drop_table("kyc_application_statuses")
