"""Pytest configuration and fixtures"""

import pytest
from mcp_router.app import app as flask_app
from mcp_router.models import db
from mcp_router.server_manager import init_server_manager
from unittest.mock import patch


@pytest.fixture(scope="session")
def app(request):
    """Session-wide test `Flask` application."""
    flask_app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "LOGIN_DISABLED": True,
        }
    )

    with flask_app.app_context():
        db.create_all()
        # Initialize the server manager for tests
        init_server_manager(flask_app)
        yield flask_app
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture(scope="function")
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture(scope="function")
def authenticated_client(client):
    """A test client that is pre-authenticated."""
    with patch("mcp_router.auth.login_required", lambda f: f):
        yield client


@pytest.fixture(scope="function")
def user():
    """Create a test user object for authentication tests."""

    class TestUser:
        def __init__(self):
            self.id = 1
            self.is_authenticated = True
            self.is_active = True
            self.is_anonymous = False

        def get_id(self):
            return str(self.id)

    return TestUser()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Fixture to ensure the database is clean before each test."""
    with app.app_context():
        meta = db.metadata
        for table in reversed(meta.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
