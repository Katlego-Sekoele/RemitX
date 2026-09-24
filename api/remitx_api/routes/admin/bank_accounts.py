"""Admin endpoints for verifying customer bank accounts.

The approval queue every new bank account passes through before it can
receive a withdrawal. Verifying or rejecting here changes the account's
status.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.controllers.bank_account_controller import BankAccountController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.bank_account import (
    BankAccountRead,
    RejectBankAccountRequest,
)
from remitx_api.models.schemas.count import CountRead
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_admin_router
from remitx_api.services.bank_account_service import (
    BankAccountNotFoundError,
    BankAccountNotPendingError,
)

router: APIRouter = create_admin_router(
    permission=PermissionCode.CASHOUT_READ,
    prefix="/admin/bank-accounts",
    tags=[Tag.ADMIN_BANK_ACCOUNTS],
)
controller = BankAccountController()


@router.get(
    "/pending",
    response_model=list[BankAccountRead],
    summary="List bank accounts awaiting verification",
)
def list_pending_bank_accounts():
    """List every bank account that is `pending_verification` and awaiting an
    admin's approval or rejection. The full account number is returned here,
    because this is an admin endpoint, but the customer-facing endpoints mask
    it for security."""
    return [BankAccountRead.model_validate(view) for view in controller.list_pending()]


@router.get(
    "/pending-count",
    response_model=CountRead,
    summary="Count bank accounts awaiting verification",
)
def get_pending_bank_account_count():
    """How many external bank accounts are `pending_verification`. Needs
    ``cashout:read``."""
    return CountRead(count=controller.pending_count())


@router.post(
    "/{bank_account_id}/verify",
    response_model=BankAccountRead,
    dependencies=[Depends(RequirePermission(PermissionCode.CASHOUT_APPROVE))],
    summary="Verify a bank account",
    responses=error_responses(400),
)
def verify_bank_account(
    bank_account_id: uuid.UUID,
    operator: User = Depends(get_current_user),
):
    """Verify a user's bank account and record who verified it."""
    try:
        view = controller.verify(bank_account_id, operator.id)
    except (BankAccountNotFoundError, BankAccountNotPendingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return BankAccountRead.model_validate(view)


@router.post(
    "/{bank_account_id}/reject",
    response_model=BankAccountRead,
    dependencies=[Depends(RequirePermission(PermissionCode.CASHOUT_FAIL))],
    summary="Reject a bank account",
    responses=error_responses(400),
)
def reject_bank_account(
    bank_account_id: uuid.UUID,
    payload: RejectBankAccountRequest,
    operator: User = Depends(get_current_user),
):
    """Reject a user's bank account and record who rejected it and why."""
    try:
        view = controller.reject(bank_account_id, operator.id, payload.reason)
    except (BankAccountNotFoundError, BankAccountNotPendingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return BankAccountRead.model_validate(view)
