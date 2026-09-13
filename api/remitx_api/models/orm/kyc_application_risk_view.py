"""`kyc_application_risk`: each application's risk assessment and what its
rating means, as a read-only view.

It reports the *stored* score — the one computed at submission — and never
recomputes it. A live recomputation would move an application's score whenever
compliance reweighted a signal, including applications an officer had already
decided on the old score, and the audit trail would stop matching the decision.
(A generated column cannot do it either: Postgres generated columns see only
their own row, and the weights live in `kyc_risk_signals`.)

What the view adds is the join every reader would otherwise repeat: the
effective rating (override if any, else computed) and that rating's
consequences from `kyc_risk_ratings`. The admin queue reads it, and so can any
reporting query.

The view is declared on its own `MetaData`, not `Base.metadata`: `create_all`
would otherwise build it as an empty table, and Alembic autogenerate would try
to manage it. The migration creates it on Postgres; the `after_create` hook
below creates it in the SQLite test database.

Postgres refuses to drop or retype a column a view selects. A later migration
that changes one of the columns below has to drop the view first and create it
again after — autogenerate will not write that for you.
"""

from sqlalchemy import (
    DDL,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
    Uuid,
    event,
)

from remitx_api.extensions import Base

VIEW_NAME = "kyc_application_risk"

# Plain SQL both dialects accept, so the tests exercise the same definition
# Postgres runs.
CREATE_VIEW_SQL = f"""
CREATE VIEW {VIEW_NAME} AS
SELECT
    a.application_id,
    a.user_id,
    a.status,
    a.submitted_at,
    a.risk_score,
    a.risk_rating AS computed_risk_rating,
    a.risk_rating_override,
    COALESCE(a.risk_rating_override, a.risk_rating) AS effective_risk_rating,
    r.severity,
    r.max_tier,
    r.limit_percent,
    r.review_interval_days,
    r.requires_senior_approval
FROM kyc_applications AS a
LEFT JOIN kyc_risk_ratings AS r
    ON r.rating = COALESCE(a.risk_rating_override, a.risk_rating)
"""

DROP_VIEW_SQL = f"DROP VIEW IF EXISTS {VIEW_NAME}"

view_metadata = MetaData()

kyc_application_risk = Table(
    VIEW_NAME,
    view_metadata,
    Column("application_id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("status", Text, nullable=False),
    Column("submitted_at", DateTime(timezone=True)),
    Column("risk_score", SmallInteger),
    Column("computed_risk_rating", Text),
    Column("risk_rating_override", Text),
    Column("effective_risk_rating", Text),
    Column("severity", SmallInteger),
    Column("max_tier", SmallInteger),
    Column("limit_percent", SmallInteger),
    Column("review_interval_days", Integer),
    Column("requires_senior_approval", Boolean),
)

event.listen(Base.metadata, "after_create", DDL(CREATE_VIEW_SQL))
event.listen(Base.metadata, "before_drop", DDL(DROP_VIEW_SQL))
