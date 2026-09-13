"""add kyc applications risk assessment

`risk_score` sits beside the existing `risk_rating`: both are computed at
submission and never written by a reviewer. A reviewer's override lands in its
own four columns — rating, reason, who, when — which a CHECK keeps all set or
all empty, so the computed and final values both survive.

Additive and nullable, so it is safe against the app version already running
(alembic/README.md rule 5).

Revision ID: a4d7b0e53f84
Revises: f3c6a9d42e73
Create Date: 2026-09-13 10:15:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

revision: str = "a4d7b0e53f84"
down_revision: str | None = "f3c6a9d42e73"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_OVERRIDE_COLUMNS = (
    "risk_rating_override",
    "risk_rating_override_reason",
    "risk_rating_overridden_by_user_id",
    "risk_rating_overridden_at",
)


def upgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.add_column(sa.Column("risk_score", sa.SmallInteger()))
        batch_op.add_column(sa.Column("risk_rating_override", sa.Text()))
        batch_op.add_column(sa.Column("risk_rating_override_reason", sa.Text()))
        batch_op.add_column(sa.Column("risk_rating_overridden_by_user_id", sa.Uuid()))
        batch_op.add_column(
            sa.Column("risk_rating_overridden_at", sa.DateTime(timezone=True))
        )
        batch_op.create_check_constraint(
            "kyc_applications_risk_score_in_range",
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
        )
        batch_op.create_check_constraint(
            "kyc_applications_risk_override_complete",
            "("
            + " AND ".join(f"{column} IS NULL" for column in _OVERRIDE_COLUMNS)
            + ") OR ("
            + " AND ".join(f"{column} IS NOT NULL" for column in _OVERRIDE_COLUMNS)
            + ")",
        )
        batch_op.create_foreign_key(
            "kyc_applications_risk_rating_override_fkey",
            "kyc_risk_ratings",
            ["risk_rating_override"],
            ["rating"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "kyc_applications_risk_rating_overridden_by_user_id_fkey",
            "users",
            ["risk_rating_overridden_by_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_constraint(
            "kyc_applications_risk_rating_overridden_by_user_id_fkey",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "kyc_applications_risk_rating_override_fkey", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "kyc_applications_risk_override_complete", type_="check"
        )
        batch_op.drop_constraint("kyc_applications_risk_score_in_range", type_="check")
        batch_op.drop_column("risk_rating_overridden_at")
        batch_op.drop_column("risk_rating_overridden_by_user_id")
        batch_op.drop_column("risk_rating_override_reason")
        batch_op.drop_column("risk_rating_override")
        batch_op.drop_column("risk_score")
