"""Shared SQL for settlement recovery (API session and worker session)."""

import uuid
from datetime import timedelta

from sqlalchemy import exists, not_, select
from sqlalchemy.orm import Session

from remitx_api.clock import utcnow
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_PENDING as TX_STATUS_PENDING,
    TYPE_TOKEN_BURN,
    Transaction,
)


def pending_settlement_quote_ids(
    session: Session, *, min_age_seconds: int
) -> list[uuid.UUID]:
    pending_burn = (
        select(Transaction.tx_id)
        .where(
            Transaction.quote_id == Remittance.quote_id,
            Transaction.type == TYPE_TOKEN_BURN,
            Transaction.status == TX_STATUS_PENDING,
        )
        .correlate(Remittance)
    )
    non_pending_leg = (
        select(Transaction.tx_id)
        .where(
            Transaction.quote_id == Remittance.quote_id,
            Transaction.status != TX_STATUS_PENDING,
        )
        .correlate(Remittance)
    )
    stmt = select(Remittance.quote_id).where(
        exists(pending_burn),
        not_(exists(non_pending_leg)),
    )
    if min_age_seconds > 0:
        cutoff = utcnow() - timedelta(seconds=min_age_seconds)
        stmt = stmt.where(Remittance.created_at <= cutoff)
    return list(session.scalars(stmt))
