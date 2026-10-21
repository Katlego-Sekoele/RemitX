"""Administrator actions on the shared stokvel vault (R3-07, #244)."""

import uuid

from celery.exceptions import TimeoutError as CeleryTimeoutError

from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    StokvelContractActionTimedOutError,
    StokvelContractAlreadyPausedError,
    StokvelContractNotPausedError,
)
from remitx_api.models.orm.audit_log import (
    STOKVEL_CONTRACT_SUBJECT_ID,
    AuditAction,
    AuditSubject,
)
from remitx_api.models.schemas.stokvel_contract import StokvelContractActionResponse
from remitx_api.services import queue_service
from remitx_api.services.audit_service import record_audit
from remitx_api.services.stokvel_contract_read import is_paused


class StokvelAdminController:
    def pause(
        self, actor_user_id: uuid.UUID, reason: str
    ) -> StokvelContractActionResponse:
        if is_paused():
            raise StokvelContractAlreadyPausedError()
        try:
            tx_hash = queue_service.run_pause_contract()
        except CeleryTimeoutError:
            self._write_pause_audit(actor_user_id, reason, None)
            raise StokvelContractActionTimedOutError() from None
        self._write_pause_audit(actor_user_id, reason, tx_hash)
        return StokvelContractActionResponse(tx_hash=tx_hash)

    def unpause(self, actor_user_id: uuid.UUID) -> StokvelContractActionResponse:
        if not is_paused():
            raise StokvelContractNotPausedError()
        try:
            tx_hash = queue_service.run_unpause_contract()
        except CeleryTimeoutError:
            self._write_unpause_audit(actor_user_id, None)
            raise StokvelContractActionTimedOutError() from None
        self._write_unpause_audit(actor_user_id, tx_hash)
        return StokvelContractActionResponse(tx_hash=tx_hash)

    @db_transaction
    def _write_pause_audit(
        self, actor_user_id: uuid.UUID, reason: str, tx_hash: str | None
    ) -> None:
        record_audit(
            actor_user_id=actor_user_id,
            action=AuditAction.STOKVEL_CONTRACT_PAUSED,
            subject_type=AuditSubject.STOKVEL_CONTRACT,
            subject_id=STOKVEL_CONTRACT_SUBJECT_ID,
            before={"paused": False},
            after={"paused": True, "tx_hash": tx_hash},
            reason=reason,
        )

    @db_transaction
    def _write_unpause_audit(
        self, actor_user_id: uuid.UUID, tx_hash: str | None
    ) -> None:
        record_audit(
            actor_user_id=actor_user_id,
            action=AuditAction.STOKVEL_CONTRACT_UNPAUSED,
            subject_type=AuditSubject.STOKVEL_CONTRACT,
            subject_id=STOKVEL_CONTRACT_SUBJECT_ID,
            before={"paused": True},
            after={"paused": False, "tx_hash": tx_hash},
        )
