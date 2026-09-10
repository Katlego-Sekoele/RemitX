from fastapi import FastAPI

from remitx_api.routes.health import router as health_router
from remitx_api.routes.integration_messages import (
    router as integration_messages_router,
)
from remitx_api.routes.users import router as users_router


def register_routers(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(integration_messages_router)
    app.include_router(users_router)
