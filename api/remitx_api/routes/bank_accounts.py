from fastapi import Depends, HTTPException, Query, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.bank_account_controller import (
    BankAccountController,
    BankAccountView,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.bank_account import (
    BankAccountCreateRequest,
    BankAccountRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.bank_account_service import UnsupportedCurrencyError

router = create_customer_router(prefix="/bank-accounts", tags=[Tag.BANK_ACCOUNTS])
controller = BankAccountController()


def _mask_account_number(account_number: str) -> str:
    """Last 4 digits only. The full number is still stored and still goes
    over the wire to the admin endpoints (an operator needs it to actually
    verify the account, see routes/admin/bank_accounts.py) — this is purely
    about not putting a customer's own full account number on their screen
    on every page load."""
    visible = account_number[-4:]
    return f"****{visible}" if len(account_number) > len(visible) else account_number


def _read(view: BankAccountView) -> BankAccountRead:
    return BankAccountRead.model_validate(view).model_copy(
        update={"account_number": _mask_account_number(view.account_number)}
    )


@router.post(
    "",
    response_model=BankAccountRead,
    summary="Add a bank account",
    responses=error_responses(400),
)
def add_bank_account(
    payload: BankAccountCreateRequest,
    user: User = Depends(get_current_user),
):
    """Stored `pending_verification` — it can't receive a withdrawal until an
    admin verifies it. See `POST /withdrawals` and the admin bank-account
    queue."""
    try:
        view = controller.add(
            user.id,
            payload.account_holder_name,
            payload.bank_name,
            payload.account_number,
            payload.currency,
            payload.branch_code,
            payload.country,
        )
    except UnsupportedCurrencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _read(view)


@router.get(
    "",
    response_model=list[BankAccountRead],
    summary="List the caller's own bank accounts",
)
def list_bank_accounts(
    currency: str | None = Query(
        None, description="e.g. ZAR — omit to list across every currency"
    ),
    user: User = Depends(get_current_user),
):
    """Every bank account this caller has added for `currency` (or for any
    currency, if omitted), whatever its status — the currency-account
    detail view, so a `pending_verification` or `rejected` account still
    shows up here even though `GET /bank-accounts/withdrawable` would skip
    it."""
    return [_read(view) for view in controller.list_for_user(user.id, currency)]


@router.get(
    "/withdrawable",
    response_model=list[BankAccountRead],
    summary="List the caller's verified bank accounts in a currency",
)
def list_withdrawable_bank_accounts(
    currency: str = Query(..., description="e.g. ZAR"),
    user: User = Depends(get_current_user),
):
    """The withdrawal page's destination picker: every bank account this
    caller can withdraw a `currency` balance into right now. Only
    `verified` accounts are returned — a `pending_verification` or
    `rejected` account can't settle a withdrawal (see
    `POST /withdrawals`), so it isn't offered as a choice here even though
    it still shows up in `GET /bank-accounts`."""
    views = controller.list_withdrawable(user.id, currency)
    return [_read(view) for view in views]
