"""add beneficiaries sender linked user unique

One beneficiary per person per sender: adding someone already in the list
answers 409 instead of listing them twice.

Existing duplicates are removed first, keeping each pair's newest row (its
payout currency and relationship are the sender's latest choice). A hard
delete is safe: nothing references `beneficiaries.beneficiary_id` — quotes
and remittances point at the recipient's user id.

Revision ID: 5b9e3c7d1f20
Revises: 8d2f6b1c4a7e
Create Date: 2026-09-22 09:30:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b9e3c7d1f20"
down_revision: str | None = "8d2f6b1c4a7e"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_CONSTRAINT = "uq_beneficiaries_sender_user_id_linked_user_id"


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM beneficiaries
        WHERE beneficiary_id IN (
            SELECT beneficiary_id FROM (
                SELECT beneficiary_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY sender_user_id, linked_user_id
                           ORDER BY created_at DESC, beneficiary_id
                       ) AS position
                FROM beneficiaries
            ) AS ranked
            WHERE ranked.position > 1
        )
        """
    )
    op.create_unique_constraint(
        _CONSTRAINT, "beneficiaries", ["sender_user_id", "linked_user_id"]
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "beneficiaries", type_="unique")
