import uuid

from fastapi import Depends, HTTPException, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.account_controller import (
    AccountController,
    UnknownAccountError,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.account import AccountRead, AccountTransactionRead
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router

router = create_customer_router(tags=[Tag.ACCOUNTS])
controller = AccountController()


@router.get(
    "/accounts",
    response_model=list[AccountRead],
    summary="List the caller's currency accounts",
)
def get_accounts(user: User = Depends(get_current_user)):
    """Every currency account the caller holds, each with its reference,
    ledger balance and available balance. ZAR comes first, then any other
    fiat currency alphabetically, then the settlement (uctusd) wallet."""
    return [
        AccountRead(
            account_id=view.account_id,
            currency=view.currency,
            reference=view.reference,
            kind=view.kind,
            balance=view.balance,
            available_balance=view.available_balance,
        )
        for view in controller.get_accounts(user.id)
    ]


@router.get(
    "/accounts-history",
    response_model=list[AccountTransactionRead],
    summary="List one account's transaction history",
    responses=error_responses(400),
)
def get_accounts_history(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Incoming and outgoing legs for one of the caller's own accounts,
    newest first — status and date included."""
    try:
        legs = controller.get_account_history(user.id, account_id)
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
        )
        for leg in legs
    ]
