"""Deny UPDATE and DELETE on audit_log (issue #54).

The application never mutates audit rows; this trigger makes that true even
for a privileged database session.

Revision ID: b3a8c1d4e5f6
Revises: a1b2c3d4e5f6
Create Date: 2026-09-26 16:00:00.000000+00:00

"""

from alembic import op

revision: str = "b3a8c1d4e5f6"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_deny_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update_or_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW
        EXECUTE FUNCTION audit_log_deny_mutation();
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_or_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_deny_mutation()")
