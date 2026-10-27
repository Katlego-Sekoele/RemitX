"""Administrator actions on the shared stokvel vault (R3-07, #244; R3-10, #247)."""

import logging
import uuid
from typing import NoReturn

from celery.exceptions import TimeoutError as CeleryTimeoutError

from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    CycleNotOpenError,
    CycleStartingError,
    RoundAlreadyFinalisedError,
    RoundNotFinalisableError,
    RoundReleaseNotPendingError,
    StokvelChainMismatchError,
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
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_payout import StokvelPayoutReleaseStatus
from remitx_api.models.schemas.stokvel_contract import (
    AdminStokvelRoundRead,
    StokvelContractActionResponse,
    StokvelContractRead,
    StokvelRoundFinaliseResponse,
)
from remitx_api.services.stokvel_admin_read import (
    list_admin_rounds,
    read_contract_status,
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

logger = logging.getLogger(__name__)

# The chain said the round cannot be sent. `release_pool` would learn the
# same thing and send nothing; the route answers before queueing.
# `NO_OPEN_CYCLE` and `UNKNOWN_STOKVEL` are not here: this route only reads
# the chain after `registered_at` is set, so those are a permanent mismatch.
_NOT_READY = {
    FinaliseReadiness.NOT_YET: RoundNotFinalisableError,
    FinaliseReadiness.ALREADY: RoundAlreadyFinalisedError,
}

_CHAIN_MISMATCH = frozenset(
    {FinaliseReadiness.NO_OPEN_CYCLE, FinaliseReadiness.UNKNOWN_STOKVEL}
)


class StokvelAdminController:
    def get_contract(self) -> StokvelContractRead:
        view = read_contract_status()
        return StokvelContractRead(
            address=view.address,
            network=view.network,
            paused=view.paused,
            paused_at=view.paused_at,
            paused_reason=view.paused_reason,
            treasury_token_balance=view.treasury_token_balance,
        )

    def list_rounds(self) -> list[AdminStokvelRoundRead]:
        return [
            AdminStokvelRoundRead(
                stokvel_id=row.stokvel_id,
                stokvel_name=row.stokvel_name,
                round=row.round,
                total_rounds=row.total_rounds,
                recipient_name=row.recipient_name,
                paid_count=row.paid_count,
                member_count=row.member_count,
                payout_time=row.payout_time,
                release_status=row.release_status,
                release_tx_hash=row.release_tx_hash,
            )
            for row in list_admin_rounds()
        ]

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
        and nothing is queued. A payout that is not `pending` is refused too:
        the worker only claims `pending`. A second queue for a round the
        chain still calls ready, whose payout is still `pending`, is
        harmless: `release_pool` claims the payout once."""
        stokvel = StokvelRepository().get_by_id(stokvel_id)
        if stokvel is None:
            raise StokvelNotFoundError()
        cycles = StokvelCycleRepository()
        cycle = cycles.get_open_cycle(stokvel_id)
        if cycle is None:
            self._refuse_after_cycle(cycles.get_latest_cycle(stokvel_id), round_)
        if cycle.status == StokvelCycleStatus.FORMING.value and cycle.cycle_number > 1:
            # The worker opens the next cycle as one closes (R2-15, #237), so
            # the round asked about is most likely the closed cycle's.
            self._refuse_after_cycle(
                cycles.get_cycle_by_number(stokvel_id, cycle.cycle_number - 1), round_
            )
        if cycle.status != StokvelCycleStatus.ACTIVE.value:
            raise CycleNotOpenError()
        if cycle.registered_at is None:
            raise CycleStartingError()
        if cycle.total_rounds is None or round_ >= cycle.total_rounds:
            raise RoundNotFinalisableError()
        if is_paused():
            raise StokvelPausedError()
        readiness = finalise_readiness(stokvel_id, cycle.cycle_number, round_)
        if readiness is not FinaliseReadiness.READY:
            self._refuse_chain(stokvel_id, cycle.cycle_number, round_, readiness)
        payout = StokvelPayoutRepository().get_round_payout(cycle.id, round_)
        if (
            payout is not None
            and payout.release_status != StokvelPayoutReleaseStatus.PENDING.value
        ):
            if payout.release_status == StokvelPayoutReleaseStatus.RELEASED.value:
                raise RoundAlreadyFinalisedError()
            raise RoundReleaseNotPendingError()
        self._enqueue_and_audit(
            actor_user_id,
            stokvel_id,
            cycle.id,
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

    def _refuse_after_cycle(
        self, previous: StokvelCycle | None, round_: int
    ) -> NoReturn:
        """A closed cycle has already released every round it had. The
        contract sets `closed` only after the last round is released."""
        if (
            previous is not None
            and previous.status == StokvelCycleStatus.CLOSED.value
            and previous.total_rounds is not None
            and round_ < previous.total_rounds
        ):
            raise RoundAlreadyFinalisedError()
        if previous is not None and previous.status == StokvelCycleStatus.CLOSED.value:
            raise RoundNotFinalisableError()
        raise CycleNotOpenError()

    def _refuse_chain(
        self,
        stokvel_id: uuid.UUID,
        cycle_number: int,
        round_: int,
        readiness: FinaliseReadiness,
    ) -> NoReturn:
        if readiness in _CHAIN_MISMATCH:
            logger.error(
                "event=stokvel.finalise_chain_mismatch stokvel_id=%s "
                "cycle_number=%s round=%s readiness=%s",
                stokvel_id,
                cycle_number,
                round_,
                readiness.value,
            )
            raise StokvelChainMismatchError()
        raise _NOT_READY[readiness]()

    @db_transaction
    def _enqueue_and_audit(
        self,
        actor_user_id: uuid.UUID,
        stokvel_id: uuid.UUID,
        cycle_id: uuid.UUID,
        cycle_number: int,
        round_: int,
        release_status: str | None,
        tx_hash: str | None,
    ) -> None:
        """Stage the audit, then queue. A failed enqueue rolls the audit
        back. A crash after the queue is sent and before this commits can
        still release with no audit row."""
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
        queue_service.enqueue_release_pool(str(cycle_id), round_)
