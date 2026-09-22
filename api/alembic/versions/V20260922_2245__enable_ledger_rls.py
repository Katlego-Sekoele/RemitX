"""enable row level security on the account-history tables

A customer reading ``GET /accounts-history`` must not resolve a quote, a
remittance, or a burn hash from an id alone. The repository predicates
repeat this for SQLite (tests). Postgres enforces it here.

``app.current_user_id`` is who is asking. ``app.is_admin_route`` is how:

- false — customer route: quotes they sent or received, remittances of
  those quotes, and transactions that touch one of their ``USER`` accounts
  or belong to one of those quotes (the burn leg moves money between
  platform accounts, so account ownership does not cover it)
- true — admin route: every row, including the admin's own. Deposit and
  settlement staff routes have to see the whole ledger. This is the
  opposite of ``kyc_applications``, which hides an officer's own file.
- empty user id — workers, migrations, unbound sessions: every row

FORCE ROW LEVEL SECURITY applies the policy even to the table owner.
Empty GUCs are the bypass for workers and alembic.

Revision ID: b4e8c1a09f62
Revises: c4a91e2b7d08
Create Date: 2026-09-22 22:45:00.000000+00:00
"""

from alembic import op

revision: str = "b4e8c1a09f62"
down_revision: str | None = "c4a91e2b7d08"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_UNBOUND_OR_ADMIN = """
COALESCE(current_setting('app.current_user_id', true), '') = ''
OR current_setting('app.is_admin_route', true) = 'true'
"""

_PARTY = """
sender_user_id::text = current_setting('app.current_user_id', true)
OR beneficiary_user_id::text = current_setting('app.current_user_id', true)
"""

_QUOTES_USING = f"""
{_UNBOUND_OR_ADMIN}
OR {_PARTY}
"""

_REMITTANCES_USING = f"""
{_UNBOUND_OR_ADMIN}
OR EXISTS (
  SELECT 1 FROM quotes
  WHERE quotes.quote_id = remittances.quote_id
    AND ({_PARTY})
)
"""

_TRANSACTIONS_USING = f"""
{_UNBOUND_OR_ADMIN}
OR EXISTS (
  SELECT 1 FROM accounts
  WHERE accounts.type = 'USER'
    AND accounts.user_id::text = current_setting('app.current_user_id', true)
    AND (
      accounts.account_id = transactions.credit_account_id
      OR accounts.account_id = transactions.debit_account_id
    )
)
OR EXISTS (
  SELECT 1 FROM quotes
  WHERE quotes.quote_id = transactions.quote_id
    AND ({_PARTY})
)
"""


def _enable(table: str, policy: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {policy} ON {table}
          USING ({expression})
          WITH CHECK ({expression})
        """
    )


def upgrade() -> None:
    _enable("quotes", "quotes_by_current_user", _QUOTES_USING)
    _enable("remittances", "remittances_by_current_user", _REMITTANCES_USING)
    _enable("transactions", "transactions_by_current_user", _TRANSACTIONS_USING)


def downgrade() -> None:
    for table, policy in (
        ("transactions", "transactions_by_current_user"),
        ("remittances", "remittances_by_current_user"),
        ("quotes", "quotes_by_current_user"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
