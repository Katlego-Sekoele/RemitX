"""Administrator actions on the shared stokvel vault (R3-07, #244; R3-10, #247)."""

import uuid

from celery.exceptions import TimeoutError as CeleryTimeoutError

from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    CycleNotOpenError,
    CycleStartingError,
    RoundAlreadyFinalisedError,
    RoundNotFinalisableError,
    StokvelContractActionTimedOutError,
    StokvelContractAlreadyPausedError,
    StokvelContractNotPausedError,
    StokvelNotFoundError,
    StokvelPausedError,
)
from remitx_api.models.orm.audit_log import (
    STOKVEL_CONTRACT_SUBJECT_ID,
    AuditAction,
    AuditSubject,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycleStatus
from remitx_api.models.schemas.stokvel_contract import (
    StokvelContractActionResponse,
    StokvelRoundFinaliseResponse,
)
from remitx_api.repositories.stokvel_cycle_repository import StokvelCycleRepository
from remitx_api.repositories.stokvel_payout_repository import StokvelPayoutRepository
from remitx_api.repositories.stokvel_repository import StokvelRepository
from remitx_api.services import queue_service
from remitx_api.services.audit_service import record_audit
from remitx_api.services.stokvel_contract_read import (
    FinaliseReadiness,
    finalise_readiness,
    is_paused,
)

# The chain said the round cannot be sent. `release_pool` would learn the
# same thing and send nothing; the route answers before queueing.
_NOT_READY = {
    FinaliseReadiness.NOT_YET: RoundNotFinalisableError,
    FinaliseReadiness.ALREADY: RoundAlreadyFinalisedError,
    FinaliseReadiness.NO_OPEN_CYCLE: CycleStartingError,
    FinaliseReadiness.UNKNOWN_STOKVEL: CycleStartingError,
}


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

    def finalise_round(
        self, actor_user_id: uuid.UUID, stokvel_id: uuid.UUID, round_: int
    ) -> StokvelRoundFinaliseResponse:
        """Queue `stokvel.release_pool` for one round of the stokvel's open
        cycle. The worker sends `finalise`; this does not. The chain is read
        first, so a round that is not ready or already released is refused
        and nothing is queued. A second queue for a round the chain still
        calls ready is harmless: `release_pool` claims the payout once."""
        stokvel = StokvelRepository().get_by_id(stokvel_id)
        if stokvel is None:
            raise StokvelNotFoundError()
        cycle = StokvelCycleRepository().get_open_cycle(stokvel_id)
        if cycle is None or cycle.status != StokvelCycleStatus.ACTIVE.value:
            raise CycleNotOpenError()
        if cycle.registered_at is None:
            raise CycleStartingError()
        if cycle.total_rounds is None or round_ >= cycle.total_rounds:
            raise RoundNotFinalisableError()
        if is_paused():
            raise StokvelPausedError()
        readiness = finalise_readiness(stokvel_id, cycle.cycle_number, round_)
        if readiness is not FinaliseReadiness.READY:
            raise _NOT_READY[readiness]()
        payout = StokvelPayoutRepository().get_round_payout(cycle.id, round_)
        # shortcut: release_pool only claims a pending payout. One left
        # `failed` is not retried by queueing it again.
        queue_service.enqueue_release_pool(str(cycle.id), round_)
        self._write_finalise_audit(
            actor_user_id,
            stokvel_id,
            cycle.cycle_number,
            round_,
            None if payout is None else payout.release_status,
            None if payout is None else payout.release_tx_hash,
        )
        return StokvelRoundFinaliseResponse(
            stokvel_id=stokvel_id,
            cycle_id=cycle.id,
            cycle_number=cycle.cycle_number,
            round=round_,
        )

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

    @db_transaction
    def _write_finalise_audit(
        self,
        actor_user_id: uuid.UUID,
        stokvel_id: uuid.UUID,
        cycle_number: int,
        round_: int,
        release_status: str | None,
        tx_hash: str | None,
    ) -> None:
        recorded = {
            "cycle_number": cycle_number,
            "round": round_,
            "release_status": release_status,
            "tx_hash": tx_hash,
        }
        record_audit(
            actor_user_id=actor_user_id,
            action=AuditAction.STOKVEL_ROUND_FINALISED_MANUALLY,
            subject_type=AuditSubject.STOKVEL,
            subject_id=stokvel_id,
            before=recorded,
            after={**recorded, "enqueued": True},
        )
