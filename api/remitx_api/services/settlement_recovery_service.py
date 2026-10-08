"""Staff-driven recovery for remittance settlement stuck off the queue.

Postgres is the source of truth; the worker's automatic reclaim only covers
groups still fully ``pending``. This module is what the admin API calls to
list non-terminal settlements and to re-enqueue ``settle_remittance`` when
that is safe.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from remitx_api.errors.settlement_recovery import (
    SettlementNotRetryableError,
    SettlementRecoveryKind,
    UnknownSettlementQuoteError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.services import queue_service
from remitx_api.settlement_recovery_queries import pending_settlement_quote_ids

logger = logging.getLogger(__name__)

SETTLEMENT_EVENT_RETRY_ENQUEUED = "settlement.retry_enqueued"
SETTLEMENT_EVENT_RECLAIM_RAN = "settlement.reclaim.ran"


@dataclass(frozen=True)
class StuckSettlement:
    quote_id: uuid.UUID
    remittance_id: uuid.UUID
    created_at: datetime
    settlement_leg_status: str
    pending_leg_count: int
    processing_leg_count: int
    failed_leg_count: int
    burn_xrpl_tx_hash: str | None
    processed_at: datetime | None
    recovery_kind: SettlementRecoveryKind


def _classify_legs(legs: list[Transaction]) -> SettlementRecoveryKind:
    statuses = {leg.status for leg in legs}
    if not legs:
        return SettlementRecoveryKind.MANUAL_ONLY
    if statuses == {STATUS_PENDING}:
        return SettlementRecoveryKind.RETRY_ENQUEUE
    if STATUS_PROCESSING in statuses:
        return SettlementRecoveryKind.MANUAL_ONLY
    if STATUS_FAILED in statuses:
        return SettlementRecoveryKind.MANUAL_ONLY
    if statuses == {STATUS_CONFIRMED}:
        return SettlementRecoveryKind.NONE
    return SettlementRecoveryKind.MANUAL_ONLY


def list_stuck_settlements(limit: int = 100) -> list[StuckSettlement]:
    """Non-terminal remittances, newest first."""
    settlement = Transaction
    rows = db.session.execute(
        select(Remittance, settlement)
        .join(settlement, settlement.tx_id == Remittance.tx_id)
        .where(settlement.status != STATUS_CONFIRMED)
        .order_by(Remittance.created_at.desc())
        .limit(limit)
    ).all()
    results: list[StuckSettlement] = []
    for remittance, settlement_leg in rows:
        legs = list(
            db.session.scalars(
                select(Transaction).where(Transaction.quote_id == remittance.quote_id)
            )
        )
        counts = {
            STATUS_PENDING: 0,
            STATUS_PROCESSING: 0,
            STATUS_FAILED: 0,
        }
        burn_hash = None
        processed_at = None
        for leg in legs:
            if leg.status in counts:
                counts[leg.status] += 1
            if leg.type == TYPE_TOKEN_BURN:
                burn_hash = leg.xrpl_tx_hash
                processed_at = leg.processed_at
        results.append(
            StuckSettlement(
                quote_id=remittance.quote_id,
                remittance_id=remittance.remittance_id,
                created_at=_as_utc(remittance.created_at),
                settlement_leg_status=settlement_leg.status,
                pending_leg_count=counts[STATUS_PENDING],
                processing_leg_count=counts[STATUS_PROCESSING],
                failed_leg_count=counts[STATUS_FAILED],
                burn_xrpl_tx_hash=burn_hash,
                processed_at=(
                    _as_utc(processed_at) if processed_at is not None else None
                ),
                recovery_kind=_classify_legs(legs),
            )
        )
    return results


def get_stuck_settlement(quote_id: uuid.UUID) -> StuckSettlement | None:
    for row in list_stuck_settlements(limit=500):
        if row.quote_id == quote_id:
            return row
    return None


def retry_enqueue(quote_id: uuid.UUID) -> None:
    """Re-queue ``settle_remittance`` when every leg is still ``pending``."""
    legs = list(
        db.session.scalars(select(Transaction).where(Transaction.quote_id == quote_id))
    )
    if not legs:
        raise UnknownSettlementQuoteError(quote_id)
    kind = _classify_legs(legs)
    if kind is not SettlementRecoveryKind.RETRY_ENQUEUE:
        raise SettlementNotRetryableError(quote_id, kind)
    queue_service.enqueue_settle_remittance(str(quote_id))
    logger.info(
        "event=%s quote_id=%s",
        SETTLEMENT_EVENT_RETRY_ENQUEUED,
        quote_id,
    )


def reclaim_fully_pending(min_age_seconds: int = 0) -> list[uuid.UUID]:
    """Re-enqueue every safe fully-``pending`` group."""
    quote_ids = pending_settlement_quote_ids(
        db.session, min_age_seconds=min_age_seconds
    )
    for quote_id in quote_ids:
        queue_service.enqueue_settle_remittance(str(quote_id))
    if quote_ids:
        logger.info(
            "event=%s count=%s min_age=%ss",
            SETTLEMENT_EVENT_RECLAIM_RAN,
            len(quote_ids),
            min_age_seconds,
        )
    return quote_ids


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
