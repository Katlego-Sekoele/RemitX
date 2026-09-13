"""create kyc onboarding catalogue

The wizard's steps, the fields and documents each step needs, and the
statuses in which an applicant may still edit a draft. Seeded so `next_step`
and resubmission pre-fill read rows rather than a tuple in the service.

Additive catalogue tables — safe against the app version already running.

Revision ID: a8d3c1e90b24
Revises: bc1240f4d035
Create Date: 2026-09-13 03:35:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.kyc_seed import (
    ONBOARDING_EDITABLE_STATUS_SEEDS,
    ONBOARDING_REQUIREMENT_SEEDS,
    ONBOARDING_STEP_SEEDS,
)

revision: str = "a8d3c1e90b24"
down_revision: str | None = "bc1240f4d035"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "kyc_onboarding_steps",
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "role IN ('entry', 'collect', 'review', 'outcome')",
            name="kyc_onboarding_steps_role_valid",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="kyc_onboarding_steps_position_non_negative",
        ),
        sa.PrimaryKeyConstraint("step"),
        sa.UniqueConstraint("position"),
    )

    steps = sa.table(
        "kyc_onboarding_steps",
        sa.column("step", sa.Text()),
        sa.column("position", sa.SmallInteger()),
        sa.column("role", sa.Text()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        steps,
        [
            {
                "step": seed.step,
                "position": seed.position,
                "role": seed.role,
                "description": seed.description,
            }
            for seed in ONBOARDING_STEP_SEEDS
        ],
    )

    op.create_table(
        "kyc_onboarding_requirements",
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("required_when", sa.Text(), nullable=False),
        sa.Column("copy_on_resubmit", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('field', 'document')",
            name="kyc_onboarding_requirements_kind_valid",
        ),
        sa.CheckConstraint(
            "required_when IN ('always', 'declares_pep', "
            "'source_of_funds_other', 'never')",
            name="kyc_onboarding_requirements_when_valid",
        ),
        sa.ForeignKeyConstraint(
            ["step"],
            ["kyc_onboarding_steps.step"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("step", "name", "kind"),
    )
    requirements = sa.table(
        "kyc_onboarding_requirements",
        sa.column("step", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("kind", sa.Text()),
        sa.column("required_when", sa.Text()),
        sa.column("copy_on_resubmit", sa.Boolean()),
    )
    op.bulk_insert(
        requirements,
        [
            {
                "step": seed.step,
                "name": seed.name,
                "kind": seed.kind,
                "required_when": seed.required_when,
                "copy_on_resubmit": seed.copy_on_resubmit,
            }
            for seed in ONBOARDING_REQUIREMENT_SEEDS
        ],
    )

    op.create_table(
        "kyc_onboarding_editable_statuses",
        sa.Column("status", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["status"],
            ["kyc_application_statuses.status"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("status"),
    )
    editable = sa.table(
        "kyc_onboarding_editable_statuses",
        sa.column("status", sa.Text()),
    )
    op.bulk_insert(
        editable,
        [{"status": status} for status in ONBOARDING_EDITABLE_STATUS_SEEDS],
    )


def downgrade() -> None:
    op.drop_table("kyc_onboarding_editable_statuses")
    op.drop_table("kyc_onboarding_requirements")
    op.drop_table("kyc_onboarding_steps")
