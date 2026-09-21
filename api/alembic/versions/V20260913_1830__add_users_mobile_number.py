"""add users mobile number

The profile page's contact mobile. Not identity evidence: the verified mobile
stays on the approved `kyc_applications` row.

NO-OP: this chain forked from the same ancestor as
V20260912_2102__add_users_last_name_mobile_number_country.py, which already
adds `users.mobile_number` (plus `last_name`/`country`) on the other branch.
Both chains are reconciled by the merge migration right after this one —
without emptying this migration's body, that merge would replay both
`add_column("users", "mobile_number")` calls and fail on Postgres with
"column already exists".

Revision ID: 63c9656baaa8
Revises: e5f81705ecd3
Create Date: 2026-09-13 18:30:00.000000+00:00

"""

revision: str = "63c9656baaa8"
down_revision: str | None = "e5f81705ecd3"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
