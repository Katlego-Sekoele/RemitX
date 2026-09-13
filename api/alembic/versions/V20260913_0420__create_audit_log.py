"""Create audit_log — who did what, to whom, and when (issue #54).

Built here because the KYC document retrieval routes (#59) must record every
look at an identity document, and a log invented per feature becomes four
shapes that answer no question between them. The table, and the single
`record_audit` helper that writes it, are the part of #54 that stands alone;
`GET /admin/audit`, the `/admin/audit` page and the database-level denial of
`UPDATE`/`DELETE` remain that ticket's.

`before`/`after` are JSONB on Postgres — containment queries over them are how
"every entry that touched this application" gets answered without a column per
subject. Both carry ids, enum values and counts, never PII: an audit log that
needs protecting as carefully as the thing it audits has defeated itself.

`actor_user_id` is never null. A system action gets its own user row rather
than a NULL, so every entry answers "who" without a special case, and the
foreign key is RESTRICT — deleting a user must not quietly erase what they did.

Revision ID: e9c14b2a7f36
Revises: d5a3b70c6e14
Create Date: 2026-09-13 04:20:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e9c14b2a7f36"
down_revision: str | None = "d5a3b70c6e14"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("before", _JSON, nullable=True),
        sa.Column("after", _JSON, nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index(
        "idx_audit_log_actor_created_at",
        "audit_log",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "idx_audit_log_subject",
        "audit_log",
        ["subject_type", "subject_id"],
    )
    op.create_index("idx_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_audit_log_created_at", table_name="audit_log")
    op.drop_index("idx_audit_log_subject", table_name="audit_log")
    op.drop_index("idx_audit_log_actor_created_at", table_name="audit_log")
    op.drop_table("audit_log")
