from fastapi import Depends, HTTPException, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.quote_controller import QuoteController
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.quote import (
    QuoteCreateRequest,
    QuotePreviewRead,
    QuotePreviewRequest,
    QuoteRead,
)
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.exchange_rate_service import (
    RateUnavailableError,
    UnsupportedCurrencyError,
)
from remitx_api.services.quote_service import (
    InsufficientBalanceError,
    KycNotApprovedError,
    LimitExceededError,
    UnknownBeneficiaryError,
)

router = create_customer_router(prefix="/quotes", tags=[Tag.QUOTES])
controller = QuoteController()


@router.post("/create-quote", response_model=QuoteRead)
def create_quote(
    payload: QuoteCreateRequest,
    user: User = Depends(get_current_user),
):
    try:
        return controller.create_quote(
            sender_user_id=user.id,
            beneficiary_id=payload.beneficiary_id,
            sender_amount=payload.sender_amount,
        )
    except KycNotApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only KYC-approved users may request a quote",
        ) from exc
    except UnknownBeneficiaryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Beneficiary not found",
        ) from exc
    except (
        LimitExceededError,
        InsufficientBalanceError,
        UnsupportedCurrencyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except RateUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exchange rate unavailable; try again shortly",
        ) from exc


@router.post("/preview-quote", response_model=QuotePreviewRead)
def preview_quote(
    payload: QuotePreviewRequest,
    # Login required; the pricing itself doesn't depend on who's asking.
    user: User = Depends(get_current_user),
):
    del user
    try:
        return controller.preview_quote(
            sender_amount=payload.sender_amount,
            sender_currency=payload.sender_currency,
            receiver_payout_currency=payload.receiver_payout_currency,
        )
    except (UnsupportedCurrencyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except RateUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exchange rate unavailable; try again shortly",
        ) from exc
