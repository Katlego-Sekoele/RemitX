from fastapi import APIRouter
from remitx_api.controllers.role_controller import RoleController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.schemas.role import RoleRead
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.ROLE_READ,
    prefix="/admin/roles",
    tags=["admin"],
)
controller = RoleController()


@router.get("", response_model=list[RoleRead])
def list_roles():
    return controller.list_roles()
