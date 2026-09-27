import uuid
from dataclasses import asdict

from fastapi import Depends, HTTPException, Query, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.remittance_controller import (
    RemittanceController,
    RemittanceView,
    TransferView,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.remittance import (
    RemittanceConfirmRequest,
    RemittanceRead,
    TransferRead,
    TransferTimelineStageRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.quote_service import UnknownBeneficiaryPayoutAccountError
from remitx_api.services.remittance_service import (
    InsufficientBalanceError,
    QuoteNotActiveError,
    QuoteNotFoundError,
)

router = create_customer_router(prefix="/remittances", tags=[Tag.REMITTANCES])
controller = RemittanceController()

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _transfer_read(view: TransferView) -> TransferRead:
    data = asdict(view)
    data["timeline"] = [
        TransferTimelineStageRead(**asdict(stage)) for stage in view.timeline
    ]
    return TransferRead(**data)


def _read(view: RemittanceView) -> RemittanceRead:
    return RemittanceRead(
        remittance_id=view.remittance_id,
        quote_id=view.quote_id,
        tx_id=view.tx_id,
        status=view.status,
        sender_amount=view.sender_amount,
        sender_currency=view.sender_currency,
        token_amount=view.token_amount,
        token_name=view.token_name,
        receiver_amount=view.receiver_amount,
        receiver_currency=view.receiver_currency,
        created_at=view.created_at,
    )


@router.post(
    "",
    response_model=RemittanceRead,
    summary="Confirm a quote and start settlement",
    responses=error_responses(400, 403, 409),
)
def confirm_remittance(
    payload: RemittanceConfirmRequest,
    user: User = Depends(get_current_user),
):
    """Turns an active quote into a remittance send: inserts its pending ledger legs and
    queues the settlement worker task. The RLUSD/uctusd transfer does not
    start until this call has committed — see Transaction_Flow_Context.md
    §2 Phase B2/C.

    Refusals: 403 if the caller is no longer KYC-verified; 400 for an unknown
    quote, a beneficiary with no fiat account in the quote's payout currency,
    or one that no longer fits the available balance or what is left of
    today's or this month's allowance (the refusal names the limit and what
    is left of it); 409 if the quote was already used or has expired. A
    refused quote stays active.
    """
    try:
        view = controller.confirm(user.id, payload.quote_id)
    except QuoteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote not found",
        ) from exc
    except QuoteNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quote is no longer active",
        ) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except UnknownBeneficiaryPayoutAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _read(view)


@router.get(
    "",
    response_model=list[TransferRead],
    summary="List the caller's transfers, sent and received",
)
def list_remittances(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    user: User = Depends(get_current_user),
):
    """Newest first. A received transfer leaves out the sender's fee lines."""
    return [_transfer_read(view) for view in controller.list_transfers(user.id, limit)]


@router.get(
    "/{remittance_id}",
    response_model=TransferRead,
    summary="Read one transfer's status and receipt",
    responses=error_responses(404),
)
def get_remittance(
    remittance_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Readable by its sender and its recipient; anyone else gets 404. Poll
    it while `status` is `pending` or `processing`."""
    return _transfer_read(controller.get_transfer(user.id, remittance_id))
