"""The signed-in customer's account overview."""

from fastapi import Depends

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.dashboard_controller import DashboardController
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.dashboard import DashboardRead
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_customer_router

router = create_customer_router(prefix="/dashboard", tags=[Tag.DASHBOARD])
controller = DashboardController()


@router.get(
    "",
    response_model=DashboardRead,
    summary="Read the caller's account overview",
)
def get_dashboard(user: User = Depends(get_current_user)):
    """Limit headroom, the last 30 UTC days of activity, in-flight transfers,
    and the people the caller has sent the most ZAR to."""
    return controller.get_dashboard(user.id)
