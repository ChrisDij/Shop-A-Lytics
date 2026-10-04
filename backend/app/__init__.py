from flask import Flask

from .config import build_config
from .extensions import db
from .routes.alerts import alerts_blueprint
from .routes.health import health_blueprint
from .routes.meta import meta_blueprint
from .routes.placeholders import placeholder_blueprint
from .routes.search import search_blueprint


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(build_config())
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.register_blueprint(health_blueprint)
    app.register_blueprint(meta_blueprint)
    app.register_blueprint(alerts_blueprint)
    app.register_blueprint(search_blueprint)
    app.register_blueprint(placeholder_blueprint)

    with app.app_context():
        from . import models  # noqa: F401

        db.create_all()

    return app
