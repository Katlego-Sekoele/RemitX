"""create kyc application risk view

`kyc_application_risk`: each application's stored score, computed rating,
override and effective rating, with that rating's consequences from
`kyc_risk_ratings`. Reports the score computed at submission and never
recomputes it — see models/orm/kyc_application_risk_view.py for why.

Views are outside `Base.metadata`, so `alembic check` neither expects nor
reports this one.

Revision ID: c6f9d2a75b06
Revises: b5e8c1f64a95
Create Date: 2026-09-13 10:25:00.000000+00:00

"""

from alembic import op
from remitx_api.models.orm.kyc_application_risk_view import (
    CREATE_VIEW_SQL,
    DROP_VIEW_SQL,
)

revision: str = "c6f9d2a75b06"
down_revision: str | None = "b5e8c1f64a95"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.execute(CREATE_VIEW_SQL)


def downgrade() -> None:
    op.execute(DROP_VIEW_SQL)
