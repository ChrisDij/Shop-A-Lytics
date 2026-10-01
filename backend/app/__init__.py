import os

from flask import Flask

from .extensions import db
from .routes.health import health_blueprint
from .routes.placeholders import placeholder_blueprint


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "local-development-only"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "sqlite:///shopalytics.sqlite"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    app.register_blueprint(health_blueprint)
    app.register_blueprint(placeholder_blueprint)

    with app.app_context():
        db.create_all()

    return app

