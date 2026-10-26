"""verification rests on the latest closed KYC application

Renewing a ``review_due`` approval inserts a new application, and the user's
verification was read from their latest application, so starting the renewal
made them unverified until it was approved. Verification now rests on the
latest *closed* application (``approved``, ``rejected`` or ``review_due``,
``CLOSED_STATUSES``): an open renewal leaves it where it was until a reviewer
decides it.

``kyc_latest_status`` (``V20261017_1820``) answered the Organiser inviting
someone with the invitee's latest application. This replaces it with
``kyc_latest_closed_status``, the status of their latest closed application,
which ``KycApplicationRepository.is_other_user_verified`` reads as
``get_standing`` does. Like the function it replaces, it is ``SECURITY
DEFINER`` and returns the status and nothing else, executable only by the app
role.

Revision ID: 64ee03433b3c
Revises: a91c4e7b2d08
Create Date: 2026-10-26 12:00:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "64ee03433b3c"
down_revision: str | None = "a91c4e7b2d08"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_APP_ROLE = "remitx_app"
_NEW = "kyc_latest_closed_status"
_OLD = "kyc_latest_status"

# `CLOSED_STATUSES` in remitx_api/models/orm/kyc_lifecycle.py, as it is now.
_CLOSED = "('approved', 'rejected', 'review_due')"


def _create(name: str, where: str) -> None:
    op.execute(
        f"""
        CREATE FUNCTION {name}(p_user_id uuid)
          RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
          SET search_path = pg_catalog, public, pg_temp
          AS $$
            SELECT status FROM kyc_applications
            WHERE user_id = p_user_id{where}
            ORDER BY created_at DESC
            LIMIT 1
          $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {name}(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {name}(uuid) TO {_APP_ROLE}")


def upgrade() -> None:
    _create(_NEW, f" AND status IN {_CLOSED}")
    op.execute(f"DROP FUNCTION IF EXISTS {_OLD}(uuid)")


def downgrade() -> None:
    _create(_OLD, "")
    op.execute(f"DROP FUNCTION IF EXISTS {_NEW}(uuid)")
