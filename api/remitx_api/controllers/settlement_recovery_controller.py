"""Staff settlement recovery: list stuck groups and re-enqueue when safe."""

import uuid

from remitx_api.db.transaction import db_transaction
from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
from remitx_api.models.schemas.settlement_recovery import (
    ReclaimPendingSettlementsResponse,
    RetrySettlementEnqueueResponse,
    StuckSettlementRead,
)
from remitx_api.services import settlement_recovery_service
from remitx_api.services.audit_service import record_audit
from remitx_api.services.settlement_recovery_service import (
    SETTLEMENT_EVENT_RECLAIM_RAN,
    SETTLEMENT_EVENT_RETRY_ENQUEUED,
    StuckSettlement,
)


class SettlementRecoveryController:
    def list_stuck(self, limit: int = 100) -> list[StuckSettlementRead]:
        rows = settlement_recovery_service.list_stuck_settlements(limit)
        return [_view(row) for row in rows]

    @db_transaction
    def retry_enqueue(
        self, actor_user_id: uuid.UUID, quote_id: uuid.UUID
    ) -> RetrySettlementEnqueueResponse:
        settlement_recovery_service.retry_enqueue(quote_id)
        record_audit(
            actor_user_id=actor_user_id,
            action=AuditAction.SETTLEMENT_RETRY_ENQUEUED,
            subject_type=AuditSubject.SETTLEMENT_QUOTE,
            subject_id=quote_id,
            after={"event": SETTLEMENT_EVENT_RETRY_ENQUEUED},
        )
        return RetrySettlementEnqueueResponse(quote_id=quote_id, enqueued=True)

    @db_transaction
    def reclaim_pending(
        self, actor_user_id: uuid.UUID, min_age_seconds: int
    ) -> ReclaimPendingSettlementsResponse:
        quote_ids = settlement_recovery_service.reclaim_fully_pending(min_age_seconds)
        for quote_id in quote_ids:
            record_audit(
                actor_user_id=actor_user_id,
                action=AuditAction.SETTLEMENT_RECLAIM_RAN,
                subject_type=AuditSubject.SETTLEMENT_QUOTE,
                subject_id=quote_id,
                after={
                    "event": SETTLEMENT_EVENT_RECLAIM_RAN,
                    "min_age_seconds": min_age_seconds,
                },
            )
        return ReclaimPendingSettlementsResponse(requeued_quote_ids=quote_ids)


def _view(row: StuckSettlement) -> StuckSettlementRead:
    return StuckSettlementRead(
        quote_id=row.quote_id,
        remittance_id=row.remittance_id,
        created_at=row.created_at,
        settlement_leg_status=row.settlement_leg_status,
        pending_leg_count=row.pending_leg_count,
        processing_leg_count=row.processing_leg_count,
        failed_leg_count=row.failed_leg_count,
        burn_xrpl_tx_hash=row.burn_xrpl_tx_hash,
        processed_at=row.processed_at,
        recovery_kind=row.recovery_kind,
    )
