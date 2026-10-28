"""stokvel payout name lookup

Product question 6 in docs/stokvel_integration.md. A stokvel's payout has no
sender user, so the recipient's transfers, dashboard and account history show
the stokvel's name where a sender's name would go. The recipient is usually
not a member, so row-level security on ``stokvels`` hides the row from them.

``stokvel_payout_name(stokvel)`` returns the name and nothing else, and only
to a customer who received a payout from that stokvel (a quote with that
``stokvel_id`` and them as ``beneficiary_user_id``). Workers, migrations and
admin routes get it as they would by reading the row. Anyone else gets NULL.

Revision ID: 9d2834001cc7
Revises: b6d1e4a7c302
Create Date: 2026-10-27 18:47:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d2834001cc7"
down_revision: str | None = "b6d1e4a7c302"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_ME = "current_setting('app.current_user_id', true)"
_APP_ROLE = "remitx_app"
_FUNCTION = "stokvel_payout_name"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION}(p_stokvel_id uuid)
          RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
          SET search_path = pg_catalog, public, pg_temp
          AS $$
        SELECT name FROM stokvels
        WHERE id = p_stokvel_id
          AND (
            COALESCE({_ME}, '') = ''
            OR current_setting('app.is_admin_route', true) = 'true'
            OR EXISTS (
              SELECT 1 FROM quotes
              WHERE stokvel_id = p_stokvel_id
                AND beneficiary_user_id::text = {_ME}
            )
          )
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION}(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FUNCTION}(uuid) TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}(uuid)")
