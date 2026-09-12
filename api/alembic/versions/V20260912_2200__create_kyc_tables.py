"""create kyc tables

Adds `kyc_applications`, `kyc_documents` and `kyc_decisions` — the KYC domain
model (issue #56). Additive only; `users` is left alone here. The two changes to
`users` are separate migrations, per alembic/README.md rule 1.

`uq_kyc_applications_one_open_per_user` is partial, which is what lets a user
accumulate rejected and approved attempts while still being held to one
application in flight. It carries `sqlite_where` as well as `postgresql_where`
so the same constraint exists in the SQLite database the test suite builds from
the ORM — with only the Postgres form it would degrade to a plain unique index
there and fire on a user's second application of any status.

Revision ID: 1112727332b0
Revises: 916c56a3b1f9
Create Date: 2026-09-12 22:00:05.810111+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1112727332b0"
down_revision: str | None = "916c56a3b1f9"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_OPEN_STATUSES = (
    "status IN ('in_progress', 'submitted', 'under_review', 'more_info_required')"
)


def upgrade() -> None:
    op.create_table(
        "kyc_applications",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="in_progress", nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("nationality", sa.Text(), nullable=True),
        sa.Column("id_type", sa.Text(), nullable=True),
        sa.Column("issuing_country", sa.Text(), nullable=True),
        sa.Column("id_number", sa.Text(), nullable=True),
        sa.Column("mobile_number", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("source_of_funds", sa.Text(), nullable=True),
        sa.Column("residential_line1", sa.Text(), nullable=True),
        sa.Column("residential_line2", sa.Text(), nullable=True),
        sa.Column("residential_city", sa.Text(), nullable=True),
        sa.Column("residential_postal_code", sa.Text(), nullable=True),
        sa.Column("residential_country", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_rating", sa.Text(), nullable=True),
        sa.Column("tier_granted", sa.SmallInteger(), nullable=True),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "id_type IS NULL OR id_type IN ('national_id', 'passport')",
            name="kyc_applications_id_type_valid",
        ),
        sa.CheckConstraint(
            "risk_rating IS NULL OR risk_rating IN ('low', 'medium', 'high')",
            name="kyc_applications_risk_rating_valid",
        ),
        sa.CheckConstraint(
            "source_of_funds IS NULL OR source_of_funds IN ('salary', "
            "'business_income', 'savings', 'investment', 'gift', 'pension', 'other')",
            name="kyc_applications_source_of_funds_valid",
        ),
        # `not_started` is absent on purpose: it is the derived answer for a
        # user with no application, so no row may hold it.
        sa.CheckConstraint(
            "status IN ('in_progress', 'submitted', 'under_review', "
            "'more_info_required', 'approved', 'rejected', 'review_due')",
            name="kyc_applications_status_valid",
        ),
        sa.CheckConstraint(
            "tier_granted IS NULL OR tier_granted >= 0",
            name="kyc_applications_tier_granted_non_negative",
        ),
        sa.CheckConstraint("version >= 1", name="kyc_applications_version_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("application_id"),
    )
    op.create_index(
        "idx_kyc_applications_status_submitted_at",
        "kyc_applications",
        ["status", "submitted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_kyc_applications_user_id"),
        "kyc_applications",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_kyc_applications_one_open_per_user",
        "kyc_applications",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text(_OPEN_STATUSES),
        sqlite_where=sa.text(_OPEN_STATUSES),
    )
    op.create_table(
        "kyc_documents",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp', "
            "'application/pdf')",
            name="kyc_documents_content_type_valid",
        ),
        sa.CheckConstraint(
            "document_type IN ('id_document', 'proof_of_address', 'selfie', "
            "'source_of_funds')",
            name="kyc_documents_document_type_valid",
        ),
        sa.CheckConstraint("length(sha256) = 64", name="kyc_documents_sha256_length"),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760",
            name="kyc_documents_size_bytes_in_range",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["kyc_applications.application_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("document_id"),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index(
        op.f("ix_kyc_documents_application_id"),
        "kyc_documents",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "uq_kyc_documents_application_sha256",
        "kyc_documents",
        ["application_id", "sha256"],
        unique=True,
    )
    op.create_table(
        "kyc_decisions",
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('under_review', 'more_info_required', 'approved', "
            "'rejected')",
            name="kyc_decisions_decision_valid",
        ),
        sa.CheckConstraint(
            "from_status IN ('in_progress', 'submitted', 'under_review', "
            "'more_info_required', 'approved', 'rejected', 'review_due')",
            name="kyc_decisions_from_status_valid",
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code IN ('identity_verified', "
            "'document_illegible', 'document_expired', 'document_missing', "
            "'details_mismatch', 'sanctions_match', 'suspected_fraud', "
            "'unsupported_jurisdiction', 'under_age', 'other')",
            name="kyc_decisions_reason_code_valid",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["kyc_applications.application_id"],
            ondelete="CASCADE",
        ),
        # RESTRICT, not SET NULL: a compliance log that forgets who decided
        # when the reviewer's account is deleted is not a compliance log.
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index(
        "idx_kyc_decisions_application_decided_at",
        "kyc_decisions",
        ["application_id", "decided_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_kyc_decisions_application_id"),
        "kyc_decisions",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_kyc_decisions_application_id"), table_name="kyc_decisions")
    op.drop_index(
        "idx_kyc_decisions_application_decided_at", table_name="kyc_decisions"
    )
    op.drop_table("kyc_decisions")
    op.drop_index("uq_kyc_documents_application_sha256", table_name="kyc_documents")
    op.drop_index(op.f("ix_kyc_documents_application_id"), table_name="kyc_documents")
    op.drop_table("kyc_documents")
    op.drop_index(
        "uq_kyc_applications_one_open_per_user",
        table_name="kyc_applications",
        postgresql_where=sa.text(_OPEN_STATUSES),
        sqlite_where=sa.text(_OPEN_STATUSES),
    )
    op.drop_index(op.f("ix_kyc_applications_user_id"), table_name="kyc_applications")
    op.drop_index(
        "idx_kyc_applications_status_submitted_at", table_name="kyc_applications"
    )
    op.drop_table("kyc_applications")
