"""quotes reference users, not accounts

`quotes.sender_account_id`/`beneficiary_account_id` froze a specific
`accounts.account_id` at quote-creation time. Replaced with
`sender_user_id`/`beneficiary_user_id` (FK `users.id`) — a quote is "from
this sender, to this beneficiary," not "from this specific ledger row";
the actual currency-scoped Account is resolved on demand wherever it's
needed (AccountRepository.get_user_account(user_id, currency)). See
models/orm/quote.py.

Drops the FK constraints Postgres auto-named when the original
`V20260912_1746__create_quotes.py` created them with no explicit name
(`<table>_<column>_fkey` is Postgres's own default), since this project
sets no custom naming convention.

Revision ID: f91d979fecaf
Revises: c04384f03c5a
Create Date: 2026-09-21 09:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f91d979fecaf"
down_revision: str | None = "c04384f03c5a"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.drop_index("ix_quotes_sender_account_id", table_name="quotes")
    op.drop_constraint("quotes_sender_account_id_fkey", "quotes", type_="foreignkey")
    op.drop_constraint(
        "quotes_beneficiary_account_id_fkey", "quotes", type_="foreignkey"
    )
    op.drop_column("quotes", "sender_account_id")
    op.drop_column("quotes", "beneficiary_account_id")

    op.add_column("quotes", sa.Column("sender_user_id", sa.Uuid(), nullable=False))
    op.add_column("quotes", sa.Column("beneficiary_user_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        "fk_quotes_sender_user_id_users", "quotes", "users", ["sender_user_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_quotes_beneficiary_user_id_users",
        "quotes",
        "users",
        ["beneficiary_user_id"],
        ["id"],
    )
    op.create_index("ix_quotes_sender_user_id", "quotes", ["sender_user_id"])


def downgrade() -> None:
    op.drop_index("ix_quotes_sender_user_id", table_name="quotes")
    op.drop_constraint(
        "fk_quotes_beneficiary_user_id_users", "quotes", type_="foreignkey"
    )
    op.drop_constraint("fk_quotes_sender_user_id_users", "quotes", type_="foreignkey")
    op.drop_column("quotes", "beneficiary_user_id")
    op.drop_column("quotes", "sender_user_id")

    op.add_column(
        "quotes", sa.Column("beneficiary_account_id", sa.Uuid(), nullable=False)
    )
    op.add_column("quotes", sa.Column("sender_account_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        "quotes_sender_account_id_fkey",
        "quotes",
        "accounts",
        ["sender_account_id"],
        ["account_id"],
    )
    op.create_foreign_key(
        "quotes_beneficiary_account_id_fkey",
        "quotes",
        "accounts",
        ["beneficiary_account_id"],
        ["account_id"],
    )
    op.create_index("ix_quotes_sender_account_id", "quotes", ["sender_account_id"])
