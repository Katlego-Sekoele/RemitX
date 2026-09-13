from fastapi import APIRouter
from remitx_api.controllers.role_controller import RoleController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.schemas.role import RoleRead, ToxicCombinationRead
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.ROLE_READ,
    prefix="/admin/roles",
    tags=[Tag.ADMIN_ROLES],
)
controller = RoleController()


@router.get("", response_model=list[RoleRead], summary="List the role catalogue")
def list_roles():
    """Every role with the permissions it carries, as the server enforces them."""
    return controller.list_roles()


@router.get(
    "/toxic-combinations",
    response_model=list[ToxicCombinationRead],
    summary="List toxic permission combinations",
)
def list_toxic_combinations():
    """Permission pairs the access page warns about before confirming a grant.

    Read from the same rows the grant is checked against, so the warning a
    granter sees cannot drift from what the server records — and so changing
    a rule is an ``UPDATE``, not a redeploy.
    """
    return controller.list_toxic_combinations()
