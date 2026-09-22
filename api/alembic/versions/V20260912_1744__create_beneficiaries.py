"""create beneficiaries

A sender's beneficiary contact (Transaction_Flow_Context.md, beneficiaries
table). Required before quotes can reference one.

Revision ID: a3f6c1d9e274
Revises: eeb69031af57
Create Date: 2026-09-12 17:44:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f6c1d9e274"
down_revision: str | None = "eeb69031af57"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "beneficiaries",
        sa.Column("beneficiary_id", sa.Uuid(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=False),
        sa.Column("linked_user_id", sa.Uuid(), nullable=False),
        sa.Column("payout_currency", sa.Text(), nullable=False),
        sa.Column("relationship", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("beneficiary_id"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["linked_user_id"], ["users.id"]),
        sa.CheckConstraint(
            "relationship IN ('partner','parent','child','sibling','relative',"
            "'friend','employee','other')",
            name="beneficiaries_relationship_valid",
        ),
        sa.CheckConstraint(
            "payout_currency IN ('USD','ZWL','NAD')",
            name="beneficiaries_payout_currency_valid",
        ),
    )
    op.create_index(
        "ix_beneficiaries_sender_user_id", "beneficiaries", ["sender_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_beneficiaries_sender_user_id", table_name="beneficiaries")
    op.drop_table("beneficiaries")
