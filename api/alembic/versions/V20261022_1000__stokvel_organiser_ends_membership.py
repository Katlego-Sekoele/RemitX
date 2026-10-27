"""stokvel members: the Organiser may end another member's membership

Ticket R2-15 (#237). When the Organiser starts a follow-on cycle, a member of
the closed cycle who never chose to continue or leave is treated as leaving:
their ``stokvel_members.left_at`` is set in the same transaction as the start.
``stokvel_members_update`` (``V20261017_1820``) let a customer update only
their own row, so the Organiser's request could not do it. It now also lets
the Organiser update rows of their own stokvel.

``stokvel_member_identity_fixed`` keeps its rules for every role and adds one
for a customer updating someone else's row (only the Organiser gets that far):
the one change allowed is setting a ``left_at`` that is still null. The paying
account, and a membership that has already ended, stay the member's own.
Same SQLSTATE 23514.

Widening a policy only allows more, so safe against the code already running
(rule 5).

Revision ID: b6d1e4a7c302
Revises: a91c4e7b2d08
Create Date: 2026-10-22 10:00:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6d1e4a7c302"
down_revision: str | None = "a91c4e7b2d08"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_ME = "current_setting('app.current_user_id', true)"
_TABLE = "stokvel_members"
_UPDATE_POLICY = "stokvel_members_update"
_TRIGGER = "stokvel_member_identity_fixed"

_OWN_ROW = f"user_id::text = {_ME}"
_OWN_ROW_OR_ORGANISER = f"{_OWN_ROW} OR stokvel_is_organiser(stokvel_id, {_ME})"

# The identity rule of `V20261017_1820`, unchanged: the downgrade restores it
# alone.
_IDENTITY_FIXED = """
          IF NEW.stokvel_id IS DISTINCT FROM OLD.stokvel_id
             OR NEW.user_id IS DISTINCT FROM OLD.user_id
             OR NEW.invitation_id IS DISTINCT FROM OLD.invitation_id
             OR NEW.joined_at IS DISTINCT FROM OLD.joined_at
             OR (OLD.left_at IS NOT NULL AND NEW.left_at IS NULL)
          THEN
            RAISE EXCEPTION
              'a stokvel membership''s stokvel, user, invitation and join time'
              ' cannot change, and a former membership cannot be reopened'
              USING ERRCODE = '23514';
          END IF;
"""

_ONLY_ENDED_BY_OTHERS = f"""
          IF COALESCE({_ME}, '') <> ''
             AND current_setting('app.is_admin_route', true)
               IS DISTINCT FROM 'true'
             AND {_ME} <> OLD.user_id::text
             AND (OLD.left_at IS NOT NULL
                  OR NEW.left_at IS NULL
                  OR NEW.account_id IS DISTINCT FROM OLD.account_id)
          THEN
            RAISE EXCEPTION
              'only the member may change their membership; the Organiser'
              ' may only end it'
              USING ERRCODE = '23514';
          END IF;
"""


def _replace_trigger_function(body: str) -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_TRIGGER}()
          RETURNS trigger LANGUAGE plpgsql
          SET search_path = pg_catalog, public, pg_temp
          AS $$
        BEGIN
        {body}
          RETURN NEW;
        END;
        $$
        """
    )


def _replace_update_policy(rule: str) -> None:
    op.execute(f"DROP POLICY {_UPDATE_POLICY} ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY {_UPDATE_POLICY} ON {_TABLE} FOR UPDATE
          USING ({_customer(rule)})
          WITH CHECK ({_customer(rule)})
        """
    )


def _customer(expression: str) -> str:
    """Workers, migrations and admin routes see every row; customers see
    ``expression``."""
    return f"""CASE
      WHEN COALESCE({_ME}, '') = ''
        OR current_setting('app.is_admin_route', true) = 'true' THEN true
      ELSE ({expression})
    END"""


def upgrade() -> None:
    _replace_trigger_function(_IDENTITY_FIXED + _ONLY_ENDED_BY_OTHERS)
    _replace_update_policy(_OWN_ROW_OR_ORGANISER)


def downgrade() -> None:
    _replace_update_policy(_OWN_ROW)
    _replace_trigger_function(_IDENTITY_FIXED)
