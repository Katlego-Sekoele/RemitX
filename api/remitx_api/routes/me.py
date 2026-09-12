from fastapi import APIRouter, Depends

from remitx_api.auth.permissions import get_effective_permissions
from remitx_api.controllers.permission_controller import PermissionController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.routes.routers import create_customer_router

router: APIRouter = create_customer_router(prefix="/me", tags=["me"])
permission_controller = PermissionController()


@router.get("/permissions", response_model=list[str])
def list_my_permissions(
    permissions: frozenset[PermissionCode] = Depends(get_effective_permissions),
):
    return permission_controller.list_for_user(permissions)
