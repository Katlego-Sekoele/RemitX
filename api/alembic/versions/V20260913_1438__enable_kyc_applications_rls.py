"""enable kyc applications row level security

``app.current_user_id`` is who is asking. ``app.is_admin_route`` is how:

- false — customer route: only their own application
- true — admin route (requires a permission): every application except theirs
- empty user id — workers, migrations, unbound sessions: every row

FORCE ROW LEVEL SECURITY applies the policy even to the table owner (the
API role). Empty GUCs are the bypass for workers and alembic.

Revision ID: e1c8a4b73d20
Revises: d7b1e4c82a19
Create Date: 2026-09-13 14:38:00.000000+00:00
"""

from alembic import op

revision: str = "e1c8a4b73d20"
down_revision: str | None = "d7b1e4c82a19"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_POLICY = "kyc_applications_by_current_user"

_USING = """
COALESCE(current_setting('app.current_user_id', true), '') = ''
OR (
  current_setting('app.is_admin_route', true) = 'true'
  AND user_id::text <> current_setting('app.current_user_id', true)
)
OR (
  current_setting('app.is_admin_route', true) <> 'true'
  AND user_id::text = current_setting('app.current_user_id', true)
)
"""


def upgrade() -> None:
    op.execute("ALTER TABLE kyc_applications ENABLE ROW LEVEL SECURITY")
    # Table owner (the API role) would otherwise bypass the policy.
    op.execute("ALTER TABLE kyc_applications FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON kyc_applications
          USING ({_USING})
          WITH CHECK ({_USING})
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON kyc_applications")
    op.execute("ALTER TABLE kyc_applications NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE kyc_applications DISABLE ROW LEVEL SECURITY")
