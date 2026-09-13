from fastapi import APIRouter, Depends

from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import get_effective_permissions
from remitx_api.controllers.permission_controller import PermissionController
from remitx_api.controllers.profile_controller import ProfileController, ProfileView
from remitx_api.controllers.role_controller import RoleController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.kyc import KycStandingRead
from remitx_api.models.schemas.me import (
    MeAccessResponse,
    MyRoleResponse,
    ProfileRead,
    ProfileUpdate,
)
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_customer_router

router: APIRouter = create_customer_router(prefix="/me", tags=[Tag.ME])
permission_controller = PermissionController()
role_controller = RoleController()
profile_controller = ProfileController()


def _profile(view: ProfileView) -> ProfileRead:
    return ProfileRead(
        email=view.email,
        mobile_number=view.mobile_number,
        kyc=KycStandingRead.model_validate(view.kyc),
    )


@router.get("", response_model=ProfileRead, summary="Get the caller's profile")
def get_my_profile(user: User = Depends(get_current_user)):
    """Contact mobile, KYC status and tier, and the daily and monthly limits
    that tier carries."""
    return _profile(profile_controller.get(user.id))


@router.patch(
    "",
    response_model=ProfileRead,
    summary="Update the caller's contact mobile",
)
def update_my_profile(
    changes: ProfileUpdate,
    user: User = Depends(get_current_user),
):
    """Verified identity is not editable here."""
    return _profile(profile_controller.update(user.id, changes))


@router.get(
    "/permissions",
    response_model=MeAccessResponse,
    summary="Get the caller's effective permissions",
)
def list_my_permissions(
    user: User = Depends(get_current_user),
    permissions: frozenset[PermissionCode] = Depends(get_effective_permissions),
):
    """The union of every active role's permissions. Drives which admin pages
    the portal shows; the server still gates each route on its own."""
    return permission_controller.get_access(user.id, permissions)


@router.get(
    "/roles",
    response_model=list[MyRoleResponse],
    summary="List the caller's roles",
)
def list_my_roles(user: User = Depends(get_current_user)):
    """Active roles only, each with the permissions it carries."""
    return role_controller.list_my_roles(user.id)
