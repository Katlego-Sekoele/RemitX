from fastapi import Depends, HTTPException, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.remittance_controller import (
    RemittanceController,
    RemittanceView,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.remittance import (
    RemittanceConfirmRequest,
    RemittanceRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.remittance_service import (
    InsufficientBalanceError,
    QuoteNotActiveError,
    QuoteNotFoundError,
)

router = create_customer_router(prefix="/remittances", tags=[Tag.REMITTANCES])
controller = RemittanceController()


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
    responses=error_responses(400, 409),
)
def confirm_remittance(
    payload: RemittanceConfirmRequest,
    user: User = Depends(get_current_user),
):
    """Turns an active quote into a send: inserts its pending ledger legs and
    queues the settlement worker task. The RLUSD/uctusd transfer does not
    start until this call has committed — see Transaction_Flow_Context.md
    §2 Phase B2/C.
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
    return _read(view)
