from flask import Flask

from relyo_api.routes.health import health_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(health_bp)
