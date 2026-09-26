import uuid
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.account_controller import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    AccountController,
    UnknownAccountError,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.account import (
    AccountOpenRequest,
    AccountRead,
    AccountTransactionRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router

router = create_customer_router(tags=[Tag.ACCOUNTS])
controller = AccountController()


def _account_read(view) -> AccountRead:
    return AccountRead(
        account_id=view.account_id,
        currency=view.currency,
        reference=view.reference,
        kind=view.kind,
        balance=view.balance,
        available_balance=view.available_balance,
    )


@router.post(
    "/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Open a currency account",
    responses=error_responses(403, 409, 422),
)
def open_account(
    payload: AccountOpenRequest,
    user: User = Depends(get_current_user),
):
    """Open a fiat payout account the caller does not hold yet. The settlement
    wallet is created at sign-up and cannot be opened here.

    Refusals: 403 if the caller is not KYC-verified; 409 if they already hold
    that currency; 422 for an unsupported currency."""
    return _account_read(controller.open_account(user.id, payload.currency.value))


@router.get(
    "/accounts",
    response_model=list[AccountRead],
    summary="List the caller's currency accounts",
)
def get_accounts(user: User = Depends(get_current_user)):
    """Every currency account the caller holds, each with its reference,
    ledger balance and available balance. ZAR comes first, then any other
    fiat currency alphabetically, then the settlement (uctusd) wallet."""
    return [_account_read(view) for view in controller.get_accounts(user.id)]


@router.get(
    "/accounts-history",
    response_model=list[AccountTransactionRead],
    summary="List one account's transaction history",
    responses=error_responses(400),
)
def get_accounts_history(
    account_id: uuid.UUID,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_HISTORY_LIMIT,
            description="Page size. A full page means there may be more.",
        ),
    ] = DEFAULT_HISTORY_LIMIT,
    before: Annotated[
        datetime | None,
        Query(
            description=(
                "Only legs created before this. Pass the last row's "
                "`created_at` to get the next page."
            ),
        ),
    ] = None,
    user: User = Depends(get_current_user),
):
    """Incoming and outgoing legs for one of the caller's own accounts,
    newest first, one page at a time. Each carries a plain-language
    description from the caller's side, and a transfer's legs also carry the
    other customer's name, the remittance id and, once confirmed, the XRPL
    Testnet burn hash. Another user's account answers 400, the same as an
    unknown one."""
    try:
        legs = controller.get_account_history(
            user.id, account_id, limit=limit, before=before
        )
    except UnknownAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account not found",
        ) from exc
    return [
        AccountTransactionRead(
            tx_id=leg.tx_id,
            type=leg.type,
            direction=leg.direction,
            amount=leg.amount,
            currency=leg.currency,
            status=leg.status,
            created_at=leg.created_at,
            confirmed_at=leg.confirmed_at,
            description=leg.description,
            counterparty_name=leg.counterparty_name,
            remittance_id=leg.remittance_id,
            xrpl_tx_hash=leg.xrpl_tx_hash,
        )
        for leg in legs
    ]
