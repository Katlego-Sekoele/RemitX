"""drop users kyc_status

The `UNVERIFIED`/`APPROVED` toggle V20260910_0900__add_user_profile_fields.py
added, superseded by `kyc_applications`. A user's KYC standing is now derived
from their applications on read (`KycApplicationRepository.get_standing`) rather
than kept as a second copy here that could disagree with the first.

This is the **contract** half of alembic/README.md rule 5, and it lands in the
same release as the code that stopped reading the column — the admin
`PATCH /admin/users/{id}/kyc-status` toggle, removed in this change and never
called by the frontend. During a rolling update the outgoing image can therefore
serve that one route against a schema without the column and answer 500 until
the rollout finishes. Accepted rather than split across two releases: the route
has no caller, and leaving the column would mean leaving a `kyc_status` in the
schema that nothing writes, which is the more expensive kind of wrong.

The old values are not recoverable, so `downgrade()` restores the column and its
constraint but resets every row to `UNVERIFIED` — see the comment there.

Revision ID: 3c8a1e6b5d72
Revises: 2b4f7c1a9e05
Create Date: 2026-09-12 22:10:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c8a1e6b5d72"
down_revision: str | None = "2b4f7c1a9e05"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    # Postgres drops `users_kyc_status_valid` with the column it constrains,
    # so there is no separate drop_constraint to make.
    op.drop_column("users", "kyc_status")


def downgrade() -> None:
    # Lossy by necessity: the pre-drop values are gone, and every row comes
    # back `UNVERIFIED`. Anyone reversing this in an environment that matters
    # has to re-derive the statuses from `kyc_applications`.
    op.add_column(
        "users",
        sa.Column(
            "kyc_status",
            sa.Text(),
            server_default="UNVERIFIED",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "users_kyc_status_valid", "users", "kyc_status IN ('UNVERIFIED', 'APPROVED')"
    )
