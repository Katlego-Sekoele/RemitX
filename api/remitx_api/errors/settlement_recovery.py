import uuid
from enum import StrEnum

from remitx_api.errors.base import ConflictError, NotFoundError


class SettlementRecoveryKind(StrEnum):
    RETRY_ENQUEUE = "retry_enqueue"
    MANUAL_ONLY = "manual_only"
    NONE = "none"


class UnknownSettlementQuoteError(NotFoundError):
    def __init__(self, quote_id: uuid.UUID) -> None:
        super().__init__(f"No remittance settlement found for quote {quote_id}.")


class SettlementNotRetryableError(ConflictError):
    def __init__(self, quote_id: uuid.UUID, kind: SettlementRecoveryKind) -> None:
        super().__init__(
            f"settlement_not_retryable: quote {quote_id} is {kind.value}; "
            "only a group whose legs are all still pending can be re-enqueued."
        )
