"""delete kyc application history rows without a status change

History records status changes only. Draft saves and risk overrides used to
append a row repeating the current status, which filled the applicant's
timeline with "In progress" once per saved step. Those writes are gone; this
removes the rows they left.

A row is removed when its status equals the previous row's for the same
application, ordered as the timeline is (`changed_at`, then `history_id`).
The first row of every application is kept, as is every row that moved the
status. Overrides lose nothing: each one is also in `kyc_assessment_audit`.

Revision ID: e5f81705ecd3
Revises: f3a9c2d15e47
Create Date: 2026-09-13 17:05:49.060467+00:00

"""

from alembic import op

revision: str = "e5f81705ecd3"
down_revision: str | None = "f3a9c2d15e47"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM kyc_application_history
        WHERE history_id IN (
            SELECT history_id
            FROM (
                SELECT
                    history_id,
                    status,
                    LAG(status) OVER (
                        PARTITION BY application_id
                        ORDER BY changed_at, history_id
                    ) AS previous_status
                FROM kyc_application_history
            ) ordered
            WHERE previous_status = status
        )
        """
    )


def downgrade() -> None:
    # The deleted rows repeated a status and carried no outcome the assessment
    # audit does not also hold; there is nothing to restore.
    pass
