"""create toxic combinations

The separation-of-duties rules the access page warns on were a tuple in
Python. As rows they can be changed while the platform runs: adding a pair,
rewording an explanation, or dropping a rule a smaller team can no longer
honour is an ``UPDATE``, not a build and a deploy.

Seeded with the two baseline pairs, keyed by uuid5 like the rest of the RBAC
catalogue (a4f8c2e91d03) so the ids are the same in every environment.

Revision ID: 0c9b5e24af71
Revises: f1d47a0c3b58
Create Date: 2026-09-12 23:10:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.rbac_seed import (
    TOXIC_COMBINATION_SEEDS,
    precompute_permission_id_given_permission_code,
    precompute_toxic_combination_id_given_permissions,
)

# revision identifiers, used by Alembic.
revision: str = "0c9b5e24af71"
down_revision: str | None = "f1d47a0c3b58"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "toxic_combinations",
        sa.Column("toxic_combination_id", sa.Uuid(), nullable=False),
        sa.Column("permission_a_id", sa.Uuid(), nullable=False),
        sa.Column("permission_b_id", sa.Uuid(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "permission_a_id <> permission_b_id",
            name="toxic_combinations_distinct_permissions",
        ),
        sa.ForeignKeyConstraint(
            ["permission_a_id"],
            ["permissions.permission_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_b_id"],
            ["permissions.permission_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("toxic_combination_id"),
        sa.UniqueConstraint(
            "permission_a_id",
            "permission_b_id",
            name="uq_toxic_combinations_pair",
        ),
    )
    op.create_index(
        op.f("ix_toxic_combinations_permission_a_id"),
        "toxic_combinations",
        ["permission_a_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_toxic_combinations_permission_b_id"),
        "toxic_combinations",
        ["permission_b_id"],
        unique=False,
    )

    toxic_combinations_table = sa.table(
        "toxic_combinations",
        sa.column("toxic_combination_id", sa.Uuid()),
        sa.column("permission_a_id", sa.Uuid()),
        sa.column("permission_b_id", sa.Uuid()),
        sa.column("explanation", sa.Text()),
    )
    op.bulk_insert(
        toxic_combinations_table,
        [
            {
                "toxic_combination_id": (
                    precompute_toxic_combination_id_given_permissions(*seed.permissions)
                ),
                "permission_a_id": precompute_permission_id_given_permission_code(
                    seed.permissions[0]
                ),
                "permission_b_id": precompute_permission_id_given_permission_code(
                    seed.permissions[1]
                ),
                "explanation": seed.explanation,
            }
            for seed in TOXIC_COMBINATION_SEEDS
        ],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_toxic_combinations_permission_b_id"),
        table_name="toxic_combinations",
    )
    op.drop_index(
        op.f("ix_toxic_combinations_permission_a_id"),
        table_name="toxic_combinations",
    )
    op.drop_table("toxic_combinations")
