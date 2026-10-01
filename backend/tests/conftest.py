import pytest

from app import create_app


@pytest.fixture()
def app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()

