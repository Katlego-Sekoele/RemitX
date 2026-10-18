"""let stokvel members see and record legs on their stokvel's account

``transactions`` row-level security (``V20260922_2245``) lets a customer route
touch a leg only if it moves money on one of the caller's ``USER`` accounts or
belongs to a quote they are party to. A stokvel contribution's token leg
(Treasury Wallet -> the stokvel's ``STOKVEL`` account, ticket R2-11) touches
neither, so the contribution API could not record it, and members could not see
their stokvel's legs (doc section 8, which also rejects reading them through a
server-side query that skips row-level security).

``transactions_by_current_user`` is left exactly as it is. Two permissive
policies are added beside it, and Postgres ORs permissive policies for the same
command together:

- ``transactions_stokvel_member_select``: a customer may read a leg on the
  ``STOKVEL`` account of a stokvel they are or were a member of (as the group
  tables let former members read).
- ``transactions_stokvel_member_insert``: a customer may record only a
  contribution's token leg: a ``stokvel_contribution`` leg from the Treasury
  Wallet (``REMITX_EVM_WALLET``) into that account, and only while they are a
  current member. Both sides are pinned, so a member cannot book any other
  account against their stokvel's.

There is no update or delete policy for these legs, so a member's session can
change or remove none of them, their own included, as the stokvel tables allow
no deletes (``V20261014_1200``, ``V20261016_0901``). Workers and admin routes
already pass the original policy. The lookups are ``SECURITY DEFINER``
functions, as for the stokvel policies, so the policies do not re-enter
row-level security on ``stokvels`` and ``stokvel_members``.

Revision ID: 3d9a61c47e20
Revises: 86264fa21295
Create Date: 2026-10-16 15:00:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d9a61c47e20"
down_revision: str | None = "86264fa21295"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_ME = "current_setting('app.current_user_id', true)"
_APP_ROLE = "remitx_app"
_SELECT_POLICY = "transactions_stokvel_member_select"
_INSERT_POLICY = "transactions_stokvel_member_insert"
_TREASURY_FUNCTION = "account_is_treasury_wallet"

_STOKVEL_ACCOUNT_MEMBERS = """
  SELECT 1 FROM stokvels
  JOIN stokvel_members ON stokvel_members.stokvel_id = stokvels.id
  WHERE stokvels.account_id = p_account_id
    AND stokvel_members.user_id::text = p_user_id
"""

# name: whether p_user_id is (or, for the first, was) a member of the stokvel
# whose STOKVEL account is p_account_id
_FUNCTIONS = {
    "stokvel_account_is_member": _STOKVEL_ACCOUNT_MEMBERS,
    "stokvel_account_is_active_member": _STOKVEL_ACCOUNT_MEMBERS
    + "    AND stokvel_members.left_at IS NULL\n",
}


def upgrade() -> None:
    for name, sql in _FUNCTIONS.items():
        op.execute(
            f"""
            CREATE FUNCTION {name}(p_account_id uuid, p_user_id text)
              RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
              SET search_path = pg_catalog, public, pg_temp
              AS $$ SELECT EXISTS ({sql}) $$
            """
        )
        op.execute(f"REVOKE ALL ON FUNCTION {name}(uuid, text) FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {name}(uuid, text) TO {_APP_ROLE}")
    # The Treasury check is a lookup function too. `accounts` has no row-level
    # security today, so a plain subquery would also work; the function keeps
    # the policy correct if it ever gets some, as for the stokvel lookups.
    op.execute(
        f"""
        CREATE FUNCTION {_TREASURY_FUNCTION}(p_account_id uuid)
          RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
          SET search_path = pg_catalog, public, pg_temp
          AS $$ SELECT EXISTS (
            SELECT 1 FROM accounts
            WHERE account_id = p_account_id AND type = 'REMITX_EVM_WALLET'
          ) $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_TREASURY_FUNCTION}(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_TREASURY_FUNCTION}(uuid) TO {_APP_ROLE}")
    op.execute(
        f"""
        CREATE POLICY {_SELECT_POLICY} ON transactions FOR SELECT
          USING (
            stokvel_account_is_member(credit_account_id, {_ME})
            OR stokvel_account_is_member(debit_account_id, {_ME})
          )
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_INSERT_POLICY} ON transactions FOR INSERT
          WITH CHECK (
            type = 'stokvel_contribution'
            AND {_TREASURY_FUNCTION}(credit_account_id)
            AND stokvel_account_is_active_member(debit_account_id, {_ME})
          )
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_INSERT_POLICY} ON transactions")
    op.execute(f"DROP POLICY IF EXISTS {_SELECT_POLICY} ON transactions")
    op.execute(f"DROP FUNCTION IF EXISTS {_TREASURY_FUNCTION}(uuid)")
    for name in reversed(_FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {name}(uuid, text)")
