from remitx_api.app import create_app


def main() -> None:
    import uvicorn

    from remitx_api.config import Config

    config = Config()
    if config.DEBUG:
        uvicorn.run(
            "remitx_api.app:create_app",
            factory=True,
            host="0.0.0.0",
            port=config.PORT,
            reload=True,
        )
    else:
        uvicorn.run(
            create_app(Config),
            host="0.0.0.0",
            port=config.PORT,
        )


__all__ = ["create_app", "main"]
