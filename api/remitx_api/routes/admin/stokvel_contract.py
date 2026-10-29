"""Emergency pause and resume for every stokvel on the vault (R3-07, #244)."""

from fastapi import Depends
from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.stokvel_admin_controller import StokvelAdminController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.stokvel_contract import (
    StokvelContractActionResponse,
    StokvelContractPauseRequest,
    StokvelContractRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_admin_router

router = create_admin_router(
    permission=PermissionCode.STOKVEL_CONTRACT_PAUSE,
    prefix="/admin/stokvel-contract",
    tags=[Tag.ADMIN_STOKVEL_CONTRACT],
)
controller = StokvelAdminController()


@router.get(
    "",
    response_model=StokvelContractRead,
    summary="Read the shared stokvel vault",
    responses=error_responses(503),
)
def get_stokvel_contract():
    """The vault address, pause state (from chain plus the latest pause audit
    entry), and treasury UCTUSD balance. Needs ``stokvel:contract:pause``."""
    return controller.get_contract()


@router.post(
    "/pause",
    response_model=StokvelContractActionResponse,
    summary="Pause every stokvel on the contract",
    responses=error_responses(409, 422, 504),
)
def pause_stokvel_contract(
    payload: StokvelContractPauseRequest,
    user: User = Depends(get_current_user),
):
    """Sends `pause()` on the vault and writes `stokvel.contract.paused` to the
    audit log. Needs ``stokvel:contract:pause``."""
    return controller.pause(user.id, payload.reason)


@router.post(
    "/unpause",
    response_model=StokvelContractActionResponse,
    summary="Resume every stokvel on the contract",
    responses=error_responses(409, 504),
)
def unpause_stokvel_contract(user: User = Depends(get_current_user)):
    """Sends `unpause()` on the vault and writes `stokvel.contract.unpaused`.
    Needs ``stokvel:contract:pause``."""
    return controller.unpause(user.id)
