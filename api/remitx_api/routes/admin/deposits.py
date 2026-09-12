"""Admin endpoints for the ZAR cash-in reconciliation job.

Gated by the cash-in permissions the `treasury_operator` role carries
(models/orm/rbac_seed.py), not by "is this caller an admin": reading the
queue and moving money against it are separate capabilities, so the router
declares the read baseline and the two mutating routes escalate to
`cashin:confirm` on top of it.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.controllers.deposit_controller import DepositController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.deposit import (
    ApproveDepositRequest,
    PendingDepositRead,
    ProcessDepositsRequest,
    ProcessedDepositRead,
)
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.CASHIN_READ,
    prefix="/admin/deposits",
    tags=["admin"],
)
controller = DepositController()


@router.post(
    "/process",
    response_model=list[ProcessedDepositRead],
    dependencies=[Depends(RequirePermission(PermissionCode.CASHIN_CONFIRM))],
)
def process_deposits(payload: ProcessDepositsRequest):
    rows = [row.model_dump() for row in payload.rows]
    return controller.process_deposits(rows)


@router.get("/pending", response_model=list[PendingDepositRead])
def list_pending_deposits():
    return controller.list_pending()


@router.post(
    "/{deposit_id}/approve",
    response_model=ProcessedDepositRead,
    dependencies=[Depends(RequirePermission(PermissionCode.CASHIN_CONFIRM))],
)
def approve_deposit(
    deposit_id: uuid.UUID,
    payload: ApproveDepositRequest,
    # Not a gate — the permission dependency above is. This is only here
    # because the resolved deposit records who confirmed it.
    operator: User = Depends(get_current_user),
):
    try:
        return controller.approve(deposit_id, payload.user_id, operator.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
