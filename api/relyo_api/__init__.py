from relyo_api.app import create_app


def main() -> None:
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
    )


__all__ = ["create_app", "main"]
