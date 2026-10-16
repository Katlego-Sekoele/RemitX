"""let stokvel members see and record legs on their stokvel's account

``transactions`` row-level security (``V20260922_2245``) lets a customer route
touch a leg only if it moves money on one of the caller's ``USER`` accounts or
belongs to a quote they are party to. A stokvel contribution's token leg
(Treasury Wallet -> the stokvel's ``STOKVEL`` account, ticket R2-11) touches
neither, so the contribution API could not record it, and members could not see
their stokvel's legs (doc section 8, which also rejects reading them through a
server-side query that skips row-level security).

This adds one clause to the policy: a leg on the ``STOKVEL`` account of a
stokvel the caller is a member of (current or former, as for the group
tables). The lookup is a ``SECURITY DEFINER`` function, as for the stokvel
policies, so the policy does not re-enter row-level security on ``stokvels``
and ``stokvel_members``. Everything else in the policy is unchanged.

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
_POLICY = "transactions_by_current_user"
_FUNCTION = "stokvel_account_is_member"

# The policy as V20260922_2245 created it.
_ORIGINAL = f"""
COALESCE({_ME}, '') = ''
OR current_setting('app.is_admin_route', true) = 'true'
OR EXISTS (
  SELECT 1 FROM accounts
  WHERE accounts.type = 'USER'
    AND accounts.user_id::text = {_ME}
    AND (
      accounts.account_id = transactions.credit_account_id
      OR accounts.account_id = transactions.debit_account_id
    )
)
OR EXISTS (
  SELECT 1 FROM quotes
  WHERE quotes.quote_id = transactions.quote_id
    AND (
      sender_user_id::text = {_ME}
      OR beneficiary_user_id::text = {_ME}
    )
)
"""

_WITH_STOKVEL_ACCOUNT = f"""{_ORIGINAL}
OR {_FUNCTION}(transactions.credit_account_id, {_ME})
OR {_FUNCTION}(transactions.debit_account_id, {_ME})
"""


def _replace_policy(expression: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON transactions")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON transactions
          USING ({expression})
          WITH CHECK ({expression})
        """
    )


def upgrade() -> None:
    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION}(p_account_id uuid, p_user_id text)
          RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
          SET search_path = pg_catalog, public, pg_temp
          AS $$
            SELECT EXISTS (
              SELECT 1 FROM stokvels
              JOIN stokvel_members ON stokvel_members.stokvel_id = stokvels.id
              WHERE stokvels.account_id = p_account_id
                AND stokvel_members.user_id::text = p_user_id
            )
          $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION}(uuid, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FUNCTION}(uuid, text) TO {_APP_ROLE}")
    _replace_policy(_WITH_STOKVEL_ACCOUNT)


def downgrade() -> None:
    _replace_policy(_ORIGINAL)
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}(uuid, text)")
