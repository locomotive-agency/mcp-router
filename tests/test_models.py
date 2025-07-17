"""Tests for database models"""

import pytest
from sqlalchemy.exc import IntegrityError
from mcp_router.models import db, MCPServer


def test_create_mcp_server(app):
    """Test creating a new MCPServer instance."""
    with app.app_context():
        server = MCPServer(
            name="test-server",
            github_url="https://github.com/test/repo",
            runtime_type="docker",
            start_command="docker run test-image",
        )
        db.session.add(server)
        db.session.commit()

        retrieved = MCPServer.query.filter_by(name="test-server").first()
        assert retrieved is not None
        assert retrieved.id is not None
        assert retrieved.is_active is True
        assert retrieved.runtime_type == "docker"


def test_env_variables_property(app):
    """Test the env_variables property saves and loads JSON correctly."""
    env_data = [{"key": "API_KEY", "value": "12345"}]
    with app.app_context():
        server = MCPServer(
            name="env-test-server",
            github_url="https://github.com/test/repo",
            runtime_type="npx",
            start_command="npx start",
            env_variables=env_data,
        )
        db.session.add(server)
        db.session.commit()

        retrieved = MCPServer.query.first()
        assert retrieved.env_variables == env_data
        # Internal storage format should be JSON-serializable string
        assert isinstance(getattr(retrieved, "_env_variables", ""), (str, type(None)))


def test_name_uniqueness(app):
    """Test that the database enforces the uniqueness constraint on the server name."""
    with app.app_context():
        server1 = MCPServer(
            name="unique-server",
            github_url="https://github.com/test/repo1",
            runtime_type="uvx",
            start_command="uvx run",
        )
        db.session.add(server1)
        db.session.commit()

        server2 = MCPServer(
            name="unique-server",
            github_url="https://github.com/test/repo2",
            runtime_type="docker",
            start_command="docker run",
        )
        db.session.add(server2)

        with pytest.raises(IntegrityError):
            db.session.commit()


def test_default_values(app):
    """Test the default values for fields like is_active and created_at."""
    with app.app_context():
        server = MCPServer(
            name="default-test",
            github_url="https://github.com/test/defaults",
            runtime_type="docker",
            start_command="docker run default",
        )
        db.session.add(server)
        db.session.commit()

        retrieved = MCPServer.query.first()
        assert retrieved.is_active is True
        assert retrieved.created_at is not None
        assert retrieved.install_command == ""
        assert retrieved.env_variables == []
