"""TrustMeBank deposit integration (optional, feature-flagged).

Revision ID: e8f1a2b3c4d5
Revises: d4c8e2a91b17
Create Date: 2026-10-28 12:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

revision: str = "e8f1a2b3c4d5"
down_revision: str | None = "d4c8e2a91b17"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "trustmebank_links",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("consent_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "trustmebank_oauth_states",
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("state"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_trustmebank_oauth_states_user_id",
        "trustmebank_oauth_states",
        ["user_id"],
    )

    op.create_table(
        "trustmebank_webhook_events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )

    op.alter_column(
        "deposits",
        "statement_fingerprint",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.add_column(
        "deposits",
        sa.Column("trustmebank_payment_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_deposits_trustmebank_payment_id",
        "deposits",
        ["trustmebank_payment_id"],
        unique=True,
    )
    op.create_check_constraint(
        "deposits_source_present",
        "deposits",
        "statement_fingerprint IS NOT NULL OR trustmebank_payment_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("deposits_source_present", "deposits", type_="check")
    op.drop_index("ix_deposits_trustmebank_payment_id", table_name="deposits")
    op.drop_column("deposits", "trustmebank_payment_id")
    op.alter_column(
        "deposits",
        "statement_fingerprint",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_table("trustmebank_webhook_events")
    op.drop_index(
        "ix_trustmebank_oauth_states_user_id", table_name="trustmebank_oauth_states"
    )
    op.drop_table("trustmebank_oauth_states")
    op.drop_table("trustmebank_links")
