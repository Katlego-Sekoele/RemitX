"""add kyc applications risk declarations

What the applicant declares that the risk rules score: the FICA §21F-§21H PEP
self-declaration (three questions, then relationship, position, country and
details), source of wealth, free text for source of funds `other`, and
expected monthly volume. `kyc_pep_relationships` is the catalogue
`pep_relationship` references, seeded in FICA's vocabulary.

Additive and nullable — drafts save partial answers — so it is safe against
the app version already running (alembic/README.md rule 5).

Revision ID: f3c6a9d42e73
Revises: e2b5f8c31d62
Create Date: 2026-09-13 10:10:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.kyc_seed import PEP_RELATIONSHIP_SEEDS

revision: str = "f3c6a9d42e73"
down_revision: str | None = "e2b5f8c31d62"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "kyc_pep_relationships",
        sa.Column("relationship", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("relationship"),
    )
    relationships = sa.table(
        "kyc_pep_relationships",
        sa.column("relationship", sa.Text()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        relationships,
        [
            {"relationship": seed.relationship, "description": seed.description}
            for seed in PEP_RELATIONSHIP_SEEDS
        ],
    )

    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.add_column(sa.Column("source_of_funds_detail", sa.Text()))
        batch_op.add_column(sa.Column("expected_monthly_volume_zar", sa.Numeric(18, 2)))
        batch_op.add_column(
            sa.Column("is_domestic_prominent_influential_person", sa.Boolean())
        )
        batch_op.add_column(
            sa.Column("is_foreign_prominent_public_official", sa.Boolean())
        )
        batch_op.add_column(sa.Column("is_pep_family_or_close_associate", sa.Boolean()))
        batch_op.add_column(sa.Column("pep_relationship", sa.Text()))
        batch_op.add_column(sa.Column("pep_position", sa.Text()))
        batch_op.add_column(sa.Column("pep_country", sa.Text()))
        batch_op.add_column(sa.Column("pep_details", sa.Text()))
        batch_op.add_column(sa.Column("source_of_wealth", sa.Text()))
        batch_op.create_check_constraint(
            "kyc_applications_expected_monthly_volume_non_negative",
            "expected_monthly_volume_zar IS NULL OR expected_monthly_volume_zar >= 0",
        )
        batch_op.create_foreign_key(
            "kyc_applications_pep_relationship_fkey",
            "kyc_pep_relationships",
            ["pep_relationship"],
            ["relationship"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_constraint(
            "kyc_applications_pep_relationship_fkey", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "kyc_applications_expected_monthly_volume_non_negative", type_="check"
        )
        batch_op.drop_column("source_of_wealth")
        batch_op.drop_column("pep_details")
        batch_op.drop_column("pep_country")
        batch_op.drop_column("pep_position")
        batch_op.drop_column("pep_relationship")
        batch_op.drop_column("is_pep_family_or_close_associate")
        batch_op.drop_column("is_foreign_prominent_public_official")
        batch_op.drop_column("is_domestic_prominent_influential_person")
        batch_op.drop_column("expected_monthly_volume_zar")
        batch_op.drop_column("source_of_funds_detail")
    op.drop_table("kyc_pep_relationships")
