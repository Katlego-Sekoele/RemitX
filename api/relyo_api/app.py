from flask import Flask

from relyo_api.config import Config
from relyo_api.extensions import db
from relyo_api.routes import register_blueprints


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    register_blueprints(app)

    if app.config["DEBUG"]:
        with app.app_context():
            import relyo_api.models.orm  # noqa: F401 — register ORM models

            db.create_all()

    return app
