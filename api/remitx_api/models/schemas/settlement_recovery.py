import uuid

from remitx_api.errors.settlement_recovery import SettlementRecoveryKind
from remitx_api.models.schemas.base import Schema, UtcDateTime


class StuckSettlementRead(Schema):
    quote_id: uuid.UUID
    remittance_id: uuid.UUID
    created_at: UtcDateTime
    settlement_leg_status: str
    pending_leg_count: int
    processing_leg_count: int
    failed_leg_count: int
    burn_xrpl_tx_hash: str | None
    processed_at: UtcDateTime | None
    recovery_kind: SettlementRecoveryKind


class ReclaimPendingSettlementsRequest(Schema):
    min_age_seconds: int = 0


class ReclaimPendingSettlementsResponse(Schema):
    requeued_quote_ids: list[uuid.UUID]


class RetrySettlementEnqueueResponse(Schema):
    quote_id: uuid.UUID
    enqueued: bool
