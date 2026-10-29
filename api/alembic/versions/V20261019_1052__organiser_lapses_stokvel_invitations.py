"""the Organiser lapses a stokvel's pending invitations when a cycle starts

Ticket R2-10. An invitation still pending when the Organiser starts a cycle
lapses (CONTEXT.md, Invitation), in the same transaction as the start, so an
invitee cannot accept between the two. The start runs on the Organiser's
customer route, but ``stokvel_invitations_update`` (``V20261017_1820``) let the
Organiser record only ``revoked``; ``lapsed`` was left to a worker.

This replaces that policy with one whose answer rule also lets the Organiser
record ``lapsed``, as themselves. Everything else is unchanged: the ``USING``
rule (the invitee or the Organiser), the invitee's ``accepted`` / ``declined``,
the Organiser's ``revoked``, and the ``stokvel_invitation_fixed`` trigger, which
still allows a status change only from ``pending``.

Revision ID: 491cf91871ac
Revises: 9ecf9bd5e4bc
Create Date: 2026-10-19 10:52:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "491cf91871ac"
down_revision: str | None = "9ecf9bd5e4bc"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_ME = "current_setting('app.current_user_id', true)"
_TABLE = "stokvel_invitations"
_POLICY = "stokvel_invitations_update"

_ORGANISER = f"stokvel_is_organiser(stokvel_id, {_ME})"
_INVITEE = f"invitee_user_id::text = {_ME}"
_WRITE = f"{_INVITEE} OR {_ORGANISER}"


def _answer(organiser_statuses: str) -> str:
    """Who may record which answer, as themselves (`V20261017_1820`)."""
    return (
        f"status_changed_by_user_id::text = {_ME} AND ("
        f"(status IN ('accepted', 'declined') AND {_INVITEE})"
        f" OR (status IN ({organiser_statuses}) AND {_ORGANISER}))"
    )


def _customer(expression: str) -> str:
    """Workers, migrations and admin routes see every row; customers see
    ``expression``."""
    return f"""CASE
      WHEN COALESCE({_ME}, '') = ''
        OR current_setting('app.is_admin_route', true) = 'true' THEN true
      ELSE ({expression})
    END"""


def _replace(organiser_statuses: str) -> None:
    op.execute(f"DROP POLICY {_POLICY} ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON {_TABLE} FOR UPDATE
          USING ({_customer(_WRITE)})
          WITH CHECK ({_customer(_answer(organiser_statuses))})
        """
    )


def upgrade() -> None:
    _replace("'revoked', 'lapsed'")


def downgrade() -> None:
    _replace("'revoked'")
