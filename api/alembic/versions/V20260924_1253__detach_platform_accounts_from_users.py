"""detach platform accounts from users

RemitX's platform accounts (bank accounts, XRPL treasury wallet, fee revenue)
carried the administering admin's ``user_id``, which is why they could only be
created by ``scripts/seed_platform_accounts.py`` once that admin had a
``users`` row. They belong to RemitX, not to a person, so ``user_id`` becomes
the customer a ``USER`` row belongs to and is NULL on every other row.

Nothing reads ``user_id`` off a platform account — every lookup by user also
filters on ``type = 'USER'``, including the ``transactions`` RLS policy — so
the running app is unaffected.

The downgrade cannot say which admin owned each row, so it restores the old
constraint only where no platform account is left: after the next revision's
downgrade on a database it seeded. Elsewhere it fails on the constraint.

Revision ID: 728add2cc9e2
Revises: d9e1a4c2b807
Create Date: 2026-09-24 12:53:05.857458+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "728add2cc9e2"
down_revision: str | None = "d9e1a4c2b807"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_CONSTRAINT = "accounts_owner_matches_type"

_ONLY_USER_ROWS_OWNED = (
    "(type = 'USER' AND user_id IS NOT NULL) OR (type <> 'USER' AND user_id IS NULL)"
)
_EXTERNAL_ROWS_UNOWNED = (
    "(type <> 'EXTERNAL' AND user_id IS NOT NULL) "
    "OR (type = 'EXTERNAL' AND user_id IS NULL)"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "accounts", type_="check")
    op.execute("UPDATE accounts SET user_id = NULL WHERE type <> 'USER'")
    op.create_check_constraint(_CONSTRAINT, "accounts", _ONLY_USER_ROWS_OWNED)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "accounts", type_="check")
    op.create_check_constraint(_CONSTRAINT, "accounts", _EXTERNAL_ROWS_UNOWNED)
