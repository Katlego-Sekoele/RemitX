"""Admin endpoints for verifying customer bank accounts.

The approval queue every new bank account passes through before it can
receive a withdrawal. Verifying or rejecting here changes the account's
status and nothing else: a withdrawal into an account that isn't `verified`
is refused outright, so no withdrawal is ever pending against one waiting
on this decision (see `bank_account_service.verify_bank_account`/
`reject_bank_account`). Gated by the payout_operator role's cashout:*
permissions (models/orm/rbac_seed.py), same pattern as
routes/admin/deposits.py.
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
    return [BankAccountRead.model_validate(view) for view in controller.list_pending()]


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
    """Needs `cashout:approve`. Records who verified it."""
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
    """Needs `cashout:fail`."""
    try:
        view = controller.reject(bank_account_id, operator.id, payload.reason)
    except (BankAccountNotFoundError, BankAccountNotPendingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return BankAccountRead.model_validate(view)
