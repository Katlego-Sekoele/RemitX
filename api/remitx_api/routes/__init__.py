from fastapi import FastAPI

from remitx_api.routes.health import router as health_router


def register_routers(app: FastAPI) -> None:
    app.include_router(health_router)
