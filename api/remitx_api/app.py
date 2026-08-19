from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.routes import register_routers


@asynccontextmanager
async def _lifespan(app: FastAPI):
    config = app.state.config
    db.init(config.DATABASE_URL)
    if config.CREATE_ALL:
        import remitx_api.models.orm  # noqa: F401 — register ORM models

        db.create_all()
    yield


def create_app(config_class: type[Config] = Config) -> FastAPI:
    config = config_class()
    app = FastAPI(lifespan=_lifespan)
    app.state.config = config

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def db_session_middleware(request: Request, call_next):
        db.open_session()
        try:
            return await call_next(request)
        finally:
            db.close_session()

    register_routers(app)
    return app
