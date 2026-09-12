from fastapi import FastAPI

from remitx_api.routes.admin.deposits import router as admin_deposits_router
from remitx_api.routes.admin.roles import router as admin_roles_router
from remitx_api.routes.beneficiaries import router as beneficiaries_router
from remitx_api.routes.admin.users import router as admin_users_router
from remitx_api.routes.health import router as health_router
from remitx_api.routes.integration_messages import (
    router as integration_messages_router,
)
from remitx_api.routes.me import router as me_router
from remitx_api.routes.quotes import router as quotes_router


def register_routers(app: FastAPI) -> None:
    # Public — no router-level auth gate.
    app.include_router(health_router)

    # Customer — every handler inherits get_current_user from the router.
    app.include_router(me_router)
    app.include_router(integration_messages_router)
    app.include_router(beneficiaries_router)
    app.include_router(quotes_router)

    # Admin — mounted under /admin with a permission declared on the router.
    app.include_router(admin_roles_router)
    app.include_router(admin_users_router)
    app.include_router(admin_deposits_router)
