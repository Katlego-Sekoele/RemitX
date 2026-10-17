"""stokvel member write rules, and lookups for invitations

Ticket R2-08. ``stokvel_members`` had one ``FOR ALL`` policy (``V20261009_1801``)
whose customer write rule was only ``user_id`` = the caller. Under it a
customer could insert themselves into any stokvel with no accepted invitation,
move their own row to another stokvel, or delete it. This replaces it with one
policy per operation, as for the cycle tables (``V20261014_1200``):

- ``SELECT``: the read rule, unchanged (your own row and your fellow members)
- ``INSERT``: your own row, and only when ``stokvel_member_can_join``: you are
  the Organiser adding yourself with no invitation (creating a stokvel, R2-07),
  or ``invitation_id`` is your accepted invitation to this stokvel. Accepting
  sets the invitation to ``accepted`` first, in the same transaction
- ``UPDATE``: your own row (leaving, changing the paying account)
- no ``DELETE`` policy, so no customer route can remove a membership

The trigger ``stokvel_member_identity_fixed`` refuses any update to
``stokvel_id``, ``user_id``, ``invitation_id`` or ``joined_at``, for every role:
leaving and rejoining makes a new row, so these never change. Like
``stokvel_member_account_is_fiat``, it raises SQLSTATE 23514.

Two lookups let a customer route answer what row-level security hides from it,
returning a value and no rows:

- ``kyc_latest_status(user)``: the status of the user's latest KYC application.
  The Organiser inviting someone cannot read the invitee's applications. The
  API decides from it whether they are verified, as ``get_standing`` does
- ``stokvel_active_member_count(stokvel)``: an invitee is not a member yet, so
  cannot read the member rows to check ``MAX_STOKVEL_MEMBERS`` when accepting

Revision ID: e09d8fb367b5
Revises: 3d9a61c47e20
Create Date: 2026-10-17 18:20:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e09d8fb367b5"
down_revision: str | None = "3d9a61c47e20"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_ME = "current_setting('app.current_user_id', true)"
_APP_ROLE = "remitx_app"
_TABLE = "stokvel_members"
_OLD_POLICY = "stokvel_members_by_current_user"
_SELECT_POLICY = "stokvel_members_select"
_INSERT_POLICY = "stokvel_members_insert"
_UPDATE_POLICY = "stokvel_members_update"
_TRIGGER = "stokvel_member_identity_fixed"

_READ = f"user_id::text = {_ME} OR stokvel_is_member(stokvel_id, {_ME})"
_OWN_ROW = f"user_id::text = {_ME}"
_JOIN = f"{_OWN_ROW} AND stokvel_member_can_join(stokvel_id, invitation_id, {_ME})"

# name(signature): (return type, body)
_FUNCTIONS = {
    "stokvel_member_can_join(p_stokvel_id uuid, p_invitation_id uuid,"
    " p_user_id text)": (
        "boolean",
        """
        SELECT CASE
          WHEN p_invitation_id IS NULL THEN EXISTS (
            SELECT 1 FROM stokvels
            WHERE id = p_stokvel_id AND organiser_user_id::text = p_user_id
          )
          ELSE EXISTS (
            SELECT 1 FROM stokvel_invitations
            WHERE id = p_invitation_id
              AND stokvel_id = p_stokvel_id
              AND invitee_user_id::text = p_user_id
              AND status = 'accepted'
          )
        END
        """,
    ),
    "kyc_latest_status(p_user_id uuid)": (
        "text",
        """
        SELECT status FROM kyc_applications
        WHERE user_id = p_user_id
        ORDER BY created_at DESC
        LIMIT 1
        """,
    ),
    "stokvel_active_member_count(p_stokvel_id uuid)": (
        "integer",
        """
        SELECT count(*)::integer FROM stokvel_members
        WHERE stokvel_id = p_stokvel_id AND left_at IS NULL
        """,
    ),
}


def _customer(expression: str) -> str:
    """Workers, migrations and admin routes see every row; customers see
    ``expression``."""
    return f"""CASE
      WHEN COALESCE({_ME}, '') = ''
        OR current_setting('app.is_admin_route', true) = 'true' THEN true
      ELSE ({expression})
    END"""


def _types(signature: str) -> str:
    """`name(p_a uuid, p_b text)` -> `name(uuid, text)`, for GRANT and DROP."""
    name, params = signature.split("(", 1)
    types = [param.split()[-1] for param in params.rstrip(")").split(",")]
    return f"{name}({', '.join(types)})"


def upgrade() -> None:
    for signature, (returns, body) in _FUNCTIONS.items():
        op.execute(
            f"""
            CREATE FUNCTION {signature}
              RETURNS {returns} LANGUAGE sql STABLE SECURITY DEFINER
              SET search_path = pg_catalog, public, pg_temp
              AS $$ {body} $$
            """
        )
        op.execute(f"REVOKE ALL ON FUNCTION {_types(signature)} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {_types(signature)} TO {_APP_ROLE}")

    op.execute(f"DROP POLICY {_OLD_POLICY} ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY {_SELECT_POLICY} ON {_TABLE} FOR SELECT
          USING ({_customer(_READ)})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_INSERT_POLICY} ON {_TABLE} FOR INSERT
          WITH CHECK ({_customer(_JOIN)})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_UPDATE_POLICY} ON {_TABLE} FOR UPDATE
          USING ({_customer(_OWN_ROW)})
          WITH CHECK ({_customer(_OWN_ROW)})
        """
    )

    op.execute(
        f"""
        CREATE FUNCTION {_TRIGGER}()
          RETURNS trigger LANGUAGE plpgsql
          SET search_path = pg_catalog, public, pg_temp
          AS $$
        BEGIN
          IF NEW.stokvel_id IS DISTINCT FROM OLD.stokvel_id
             OR NEW.user_id IS DISTINCT FROM OLD.user_id
             OR NEW.invitation_id IS DISTINCT FROM OLD.invitation_id
             OR NEW.joined_at IS DISTINCT FROM OLD.joined_at
          THEN
            RAISE EXCEPTION
              'a stokvel membership''s stokvel, user, invitation and join time'
              ' cannot change'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_TRIGGER}() FROM PUBLIC")
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
          BEFORE UPDATE ON {_TABLE}
          FOR EACH ROW EXECUTE FUNCTION {_TRIGGER}()
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON {_TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER}()")
    for policy in (_UPDATE_POLICY, _INSERT_POLICY, _SELECT_POLICY):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY {_OLD_POLICY} ON {_TABLE}
          USING ({_customer(_READ)})
          WITH CHECK ({_customer(_OWN_ROW)})
        """
    )
    for signature in reversed(_FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {_types(signature)}")
