"""Admin endpoints for the ZAR cash-in reconciliation job.

Gated by the cash-in permissions the `treasury_operator` role carries
(models/orm/rbac_seed.py), not by "is this caller an admin": reading the
queue and moving money against it are separate capabilities, so the router
declares the read baseline and the two mutating routes escalate to
`cashin:confirm` on top of it.
"""

import uuid

from fastapi import APIRouter, Depends
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.controllers.deposit_controller import DepositController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.deposit import (
    AccountReferenceRead,
    ApproveDepositRequest,
    PendingDepositRead,
    ProcessDepositsRequest,
    ProcessDepositsResponse,
    ProcessedDepositRead,
    SkippedStatementLineRead,
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
)
def process_deposits(payload: ProcessDepositsRequest):
    """Rows whose reference matches a user are confirmed and credited; the rest
    wait in the pending queue for manual matching. Needs ``cashin:confirm``."""
    rows = [row.model_dump() for row in payload.rows]
    return controller.process_deposits(rows)


@router.get(
    "/account-references",
    response_model=list[AccountReferenceRead],
    summary="List customer account references",
)
def list_account_references():
    """References a statement line can match, for the cash-in editor.
    Needs ``cashin:read``. Names are display names, not email addresses."""
    return controller.list_account_references()


@router.get(
    "/pending",
    response_model=list[PendingDepositRead],
    summary="List deposits awaiting manual matching",
)
def list_pending_deposits():
    """Deposits whose reference matched no user."""
    return controller.list_pending()


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
    # Not a gate — the permission dependency above is. This is only here
    # because the resolved deposit records who confirmed it.
    operator: User = Depends(get_current_user),
):
    """Confirms the deposit against the customer who holds
    ``account_reference``. The credit lands on their ZAR account. Needs
    ``cashin:confirm``."""
    return controller.approve(deposit_id, payload.account_reference, operator.id)
