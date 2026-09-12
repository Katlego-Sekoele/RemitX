import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from remitx_api.auth.dependencies import require_admin
from remitx_api.controllers.user_controller import UnknownUserError, UserController
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.user import KycStatusUpdate, UserRead

router = APIRouter(prefix="/admin/users", tags=["admin"])
controller = UserController()


@router.patch("/{user_id}/kyc-status", response_model=UserRead)
def update_kyc_status(
    user_id: uuid.UUID,
    payload: KycStatusUpdate,
    admin: User = Depends(require_admin),
):
    try:
        return controller.set_kyc_status(user_id, payload.kyc_status)
    except UnknownUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc
