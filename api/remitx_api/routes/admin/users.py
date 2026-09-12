"""Admin endpoints for customer records.

The KYC toggle is gated on `kyc:application:decide` — the permission the
`compliance_officer` role carries (models/orm/rbac_seed.py) — because
approving or rejecting a customer's KYC is a compliance decision, not
something every staff role should be able to make.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from remitx_api.controllers.user_controller import UnknownUserError, UserController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.schemas.user import KycStatusUpdate, UserRead
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.KYC_APPLICATION_DECIDE,
    prefix="/admin/users",
    tags=["admin"],
)
controller = UserController()


@router.patch("/{user_id}/kyc-status", response_model=UserRead)
def update_kyc_status(user_id: uuid.UUID, payload: KycStatusUpdate):
    try:
        return controller.set_kyc_status(user_id, payload.kyc_status)
    except UnknownUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc
