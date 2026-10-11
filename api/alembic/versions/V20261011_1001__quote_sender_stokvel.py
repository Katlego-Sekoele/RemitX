"""quote sender can be a stokvel

Ticket R3-02 (#239), decision D6 in docs/stokvel_integration.md: a stokvel's
payout is a normal remittance with the stokvel as sender. Its quote has no
sending user, so ``quotes.sender_user_id`` becomes nullable and
``quotes.stokvel_id`` names the sending stokvel. ``quotes_one_sender``
requires exactly one of the two.

Safe against the code already running: it always sets ``sender_user_id`` and
never ``stokvel_id``, which the new CHECK allows.

The downgrade fails on ``NOT NULL`` if a stokvel quote exists, rather than
deleting it.

Revision ID: 7895afbbf058
Revises: 4fb6bcc07236
Create Date: 2026-10-11 10:01:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7895afbbf058"
down_revision: str | None = "4fb6bcc07236"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("stokvel_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_quotes_stokvel_id"), "quotes", ["stokvel_id"])
    op.create_foreign_key(
        "quotes_stokvel_id_fkey", "quotes", "stokvels", ["stokvel_id"], ["id"]
    )
    op.alter_column("quotes", "sender_user_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        "quotes_one_sender",
        "quotes",
        "(sender_user_id IS NULL) <> (stokvel_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("quotes_one_sender", "quotes", type_="check")
    op.alter_column("quotes", "sender_user_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint("quotes_stokvel_id_fkey", "quotes", type_="foreignkey")
    op.drop_index(op.f("ix_quotes_stokvel_id"), table_name="quotes")
    op.drop_column("quotes", "stokvel_id")
