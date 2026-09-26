"""deposit fingerprint occurrence suffix

Statement-line fingerprints now end with ``|#N`` (N = 0, 1, … among identical
lines in one upload) unless the line carries a bank ``line_id``. Existing rows
get ``|#0`` so re-uploading a statement that was already reconciled still
matches. Legacy keys and ``id:…`` line-id keys are left unchanged.

Downgrading strips the suffix and fails if two lines then share the same key.

Revision ID: a1b2c3d4e5f6
Revises: d7ea832b9596
Create Date: 2026-09-26 17:00:00+00:00

"""

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "d7ea832b9596"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE deposits
        SET statement_fingerprint = statement_fingerprint || '|#0'
        WHERE statement_fingerprint NOT LIKE 'legacy:%'
          AND statement_fingerprint NOT LIKE 'id:%'
          AND statement_fingerprint NOT LIKE '%|#%'
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        UPDATE deposits
        SET statement_fingerprint = regexp_replace(
            statement_fingerprint, '\|#[0-9]+$', ''
        )
        WHERE statement_fingerprint NOT LIKE 'legacy:%'
          AND statement_fingerprint NOT LIKE 'id:%'
        """
    )
