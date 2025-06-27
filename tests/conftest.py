"""Pytest configuration and fixtures"""

import pytest
from mcp_router.app import app as flask_app
from mcp_router.models import db, MCPServer

@pytest.fixture(scope='session')
def app():
    """Session-wide test `Flask` application."""
    # Setup
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,  # Disable CSRF for testing forms
        "LOGIN_DISABLED": True,  # Disable Flask-Login for testing
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.drop_all()

@pytest.fixture()
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture()
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()

@pytest.fixture(autouse=True)
def clean_db(app):
    """Fixture to ensure the database is clean before each test."""
    with app.app_context():
        # Truncate all tables
        meta = db.metadata
        for table in reversed(meta.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit() 