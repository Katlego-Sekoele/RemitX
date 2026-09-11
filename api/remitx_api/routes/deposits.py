import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from remitx_api.auth.dependencies import require_admin
from remitx_api.controllers.deposit_controller import DepositController
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.deposit import (
    ApproveDepositRequest,
    PendingDepositRead,
    ProcessDepositsRequest,
    ProcessedDepositRead,
)

router = APIRouter(prefix="/admin/deposits", tags=["admin"])
controller = DepositController()


@router.post("/process", response_model=list[ProcessedDepositRead])
def process_deposits(
    payload: ProcessDepositsRequest,
    admin: User = Depends(require_admin),
):
    rows = [row.model_dump() for row in payload.rows]
    return controller.process_deposits(rows)


@router.get("/pending", response_model=list[PendingDepositRead])
def list_pending_deposits(admin: User = Depends(require_admin)):
    return controller.list_pending()


@router.post("/{deposit_id}/approve", response_model=ProcessedDepositRead)
def approve_deposit(
    deposit_id: uuid.UUID,
    payload: ApproveDepositRequest,
    admin: User = Depends(require_admin),
):
    try:
        return controller.approve(deposit_id, payload.user_id, admin.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
