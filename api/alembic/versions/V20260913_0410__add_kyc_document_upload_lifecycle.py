"""Add the pending → stored lifecycle to kyc_documents (issue #59).

A document row is written before its bytes exist: `POST /kyc/documents`
records the declaration and hands back a signed upload URL, and only the
completion call — which reads the object back, checks its real size and sniffs
its real content type — promotes the row to `stored`. That makes three changes
to the table:

- `status`, so a row that nobody has verified can be told apart from evidence;
- `stored_at`, the moment bytes arrived and passed verification (`uploaded_at`
  is when the upload was *requested*);
- `sha256` becomes nullable, because there is nothing honest to put there
  before the object has been read.

Existing rows predate the column and all carry a digest, so they are stored by
definition; the backfill says so rather than leaving them `pending`, which
would hide real evidence from every reviewer. The column and the statement
that makes it true of rows already in the table are one change.

`kyc_documents_stored_has_digest` is the invariant the whole two-step flow
exists to protect: a row claiming to be stored has been hashed. Cheap to
enforce here, and this is exactly the kind of bug — a half-applied completion
— that is invisible without it.

Revision ID: d5a3b70c6e14
Revises: c7f2a91e4b18
Create Date: 2026-09-13 04:10:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5a3b70c6e14"
down_revision: str | None = "c7f2a91e4b18"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column(
        "kyc_documents",
        sa.Column(
            "status",
            sa.Text(),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "kyc_documents",
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "kyc_documents",
        "sha256",
        existing_type=sa.Text(),
        nullable=True,
    )

    op.execute(
        "UPDATE kyc_documents "
        "SET status = 'stored', stored_at = uploaded_at "
        "WHERE sha256 IS NOT NULL"
    )

    op.create_check_constraint(
        "kyc_documents_status_valid",
        "kyc_documents",
        "status IN ('pending', 'stored')",
    )
    # Superseded: the old form forbade the NULL a pending row must carry.
    op.drop_constraint(
        "kyc_documents_sha256_length",
        "kyc_documents",
        type_="check",
    )
    op.create_check_constraint(
        "kyc_documents_sha256_length",
        "kyc_documents",
        "sha256 IS NULL OR length(sha256) = 64",
    )
    op.create_check_constraint(
        "kyc_documents_stored_has_digest",
        "kyc_documents",
        "status <> 'stored' OR (sha256 IS NOT NULL AND stored_at IS NOT NULL)",
    )


def downgrade() -> None:
    # A pending row has no digest, so it cannot survive a NOT NULL sha256.
    # Dropping those rows is the only reversal available; the objects they
    # point at were never verified and are not evidence of anything.
    op.execute("DELETE FROM kyc_documents WHERE sha256 IS NULL")

    op.drop_constraint(
        "kyc_documents_stored_has_digest",
        "kyc_documents",
        type_="check",
    )
    op.drop_constraint(
        "kyc_documents_sha256_length",
        "kyc_documents",
        type_="check",
    )
    op.create_check_constraint(
        "kyc_documents_sha256_length",
        "kyc_documents",
        "length(sha256) = 64",
    )
    op.drop_constraint(
        "kyc_documents_status_valid",
        "kyc_documents",
        type_="check",
    )
    op.alter_column(
        "kyc_documents",
        "sha256",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("kyc_documents", "stored_at")
    op.drop_column("kyc_documents", "status")
