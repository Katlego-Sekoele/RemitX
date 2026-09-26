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
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.exchange_rate_service import (
    RateUnavailableError,
    UnsupportedCurrencyError,
)
from remitx_api.services.quote_service import (
    InsufficientBalanceError,
    UnknownBeneficiaryError,
    UnknownBeneficiaryPayoutAccountError,
    UnknownSenderAccountError,
)

router = create_customer_router(prefix="/quotes", tags=[Tag.QUOTES])
controller = QuoteController()


@router.post(
    "/create-quote",
    response_model=QuoteRead,
    summary="Lock in a price for a transfer to a beneficiary",
    responses=error_responses(400, 403, 503),
)
def create_quote(
    payload: QuoteCreateRequest,
    user: User = Depends(get_current_user),
):
    """Prices `sender_amount` for one of the caller's beneficiaries and holds
    that price until `expires_at` (QUOTE_TTL_MINUTES). Nothing is spent until
    the quote is confirmed with `POST /remittances`.

    Refusals: 403 if the caller isn't KYC-verified; 400 for an unknown
    beneficiary, a payout currency the beneficiary has no account for, a
    `sender_currency` with no account, an
    amount over what is left of today's or this month's allowance (tier
    limits scaled by the risk rating, less what was already sent), the
    available balance, or one too small to cover the fees; 503 when no
    exchange rate is available. A limit refusal names the limit and what is
    left of it.
    """
    try:
        return controller.create_quote(
            sender_user_id=user.id,
            beneficiary_id=payload.beneficiary_id,
            sender_amount=payload.sender_amount,
            sender_currency=payload.sender_currency,
            receiver_payout_currency=payload.receiver_payout_currency,
        )
    except UnknownBeneficiaryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Beneficiary not found",
        ) from exc
    except UnknownSenderAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have no account in sender_currency",
        ) from exc
    except UnknownBeneficiaryPayoutAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (
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


@router.post(
    "/preview-quote",
    response_model=QuotePreviewRead,
    summary="Price an amount without holding it",
    responses=error_responses(400, 503),
)
def preview_quote(
    payload: QuotePreviewRequest,
    # Login required; the pricing itself doesn't depend on who's asking.
    user: User = Depends(get_current_user),
):
    """An indicative price for the send form: the same pricing as a quote,
    with no beneficiary, no balance or limit checks, and nothing saved.

    Refusals: 400 for an amount too small to cover the fees or an
    unsupported currency; 503 when no exchange rate is available.
    """
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
