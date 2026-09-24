"""Admin endpoints for the cash-in reconciliation job.

Gated by the cash-in permissions.
"""

import uuid

from fastapi import APIRouter, Depends
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.controllers.deposit_controller import DepositController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.count import CountRead
from remitx_api.models.schemas.deposit import (
    AccountReferenceRead,
    ApproveDepositRequest,
    PendingDepositRead,
    ProcessDepositsRequest,
    ProcessDepositsResponse,
    ProcessedDepositRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.CASHIN_READ,
    prefix="/admin/deposits",
    tags=[Tag.ADMIN_DEPOSITS],
)
controller = DepositController()


@router.post(
    "/process",
    response_model=ProcessDepositsResponse,
    dependencies=[Depends(RequirePermission(PermissionCode.CASHIN_CONFIRM))],
    summary="Reconcile bank-statement rows into deposits",
    responses=error_responses(409),
)
def process_deposits(payload: ProcessDepositsRequest):
    """Each row carries the currency of the RemitX bank account it came into.
    Rows whose reference names the customer's account in that currency are
    confirmed and credited. The rest, including references to an account in
    another currency, wait in the pending queue for manual matching. Rows
    with no currency RemitX banks in are skipped. Needs ``cashin:confirm``."""
    rows = [row.model_dump() for row in payload.rows]
    return controller.process_deposits(rows)


@router.get(
    "/account-references",
    response_model=list[AccountReferenceRead],
    summary="List customer account references",
)
def list_account_references():
    """References a deposit can land on, for the cash-in editor: every
    customer fiat account, never a token account. Needs ``cashin:read``.
    Names are display names, not email addresses."""
    return controller.list_account_references()


@router.get(
    "/pending",
    response_model=list[PendingDepositRead],
    summary="List deposits awaiting manual matching",
)
def list_pending_deposits():
    """Deposits whose reference matched no user."""
    return controller.list_pending()


@router.get(
    "/pending-count",
    response_model=CountRead,
    summary="Count deposits awaiting manual matching",
)
def get_pending_deposit_count():
    """How many statement lines are still unmatched. Needs ``cashin:read``."""
    return CountRead(count=controller.pending_count())


@router.post(
    "/{deposit_id}/approve",
    response_model=ProcessedDepositRead,
    dependencies=[Depends(RequirePermission(PermissionCode.CASHIN_CONFIRM))],
    summary="Match a pending deposit to a user",
    responses=error_responses(400),
)
def approve_deposit(
    deposit_id: uuid.UUID,
    payload: ApproveDepositRequest,
    operator: User = Depends(get_current_user),
):
    """Confirms the deposit against the account ``account_reference`` names,
    which must be in the deposit's currency. Needs ``cashin:confirm``."""
    return controller.approve(deposit_id, payload.account_reference, operator.id)
