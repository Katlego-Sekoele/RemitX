from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from remitx_api.config import Config
from remitx_api.errors.base import DomainError
from remitx_api.extensions import db
from remitx_api.middleware import MaxBodySizeMiddleware, RequestIdMiddleware
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

    # Starlette runs the *last* middleware added outermost, so this reads
    # inside out: CORS, then the request id, then the body guard, then
    # routing. CORS has to stay outside the guard — a 413 without CORS
    # headers reaches the browser as an opaque network error rather than as
    # the refusal it is — and the guard has to stay outside routing, so an
    # oversized body costs nothing even on a path that does not exist.
    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        """Turn a refusal expressed in the domain's terms into HTTP.

        Registered once here rather than repeated as a ``try``/``except`` in
        every route: a mapping a handler forgets is a 500 the caller cannot
        act on, and routes are supposed to be HTTP only. The body matches
        ``HTTPException``'s so a client sees one error shape.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.middleware("http")
    async def db_session_middleware(request: Request, call_next):
        token = db.open_session()
        try:
            return await call_next(request)
        finally:
            db.close_session(token)

    register_routers(app)
    return app
