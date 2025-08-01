
import unittest
from flask import Flask
from mcp_router.models import (
    db,
    init_db,
    MCPServer,
    MCPServerStatus,
    get_active_servers,
    get_auth_type,
    set_auth_type,
    ensure_server_status_exists,
)
from mcp_router.config import TestingConfig


class TestModels(unittest.TestCase):
    """Test cases for the database models."""

    def setUp(self):
        """Set up a test Flask application and initialize the database."""
        self.app = Flask(__name__)
        self.app.config.from_object(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        init_db(self.app)

    def tearDown(self):
        """Tear down the database session and application context."""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_create_mcp_server(self):
        """Test the creation of an MCPServer instance."""
        server = MCPServer(
            name="Test Server",
            github_url="https://github.com/example/test",
            runtime_type="docker",
            start_command="docker run test",
        )
        db.session.add(server)
        db.session.commit()

        retrieved_server = MCPServer.query.filter_by(name="Test Server").first()
        self.assertIsNotNone(retrieved_server)
        self.assertEqual(retrieved_server.name, "Test Server")
        self.assertEqual(retrieved_server.build_status, "pending")
        self.assertTrue(retrieved_server.is_active)

    def test_mcp_server_to_dict(self):
        """Test the to_dict method of the MCPServer model."""
        server = MCPServer(
            name="Dict Test Server",
            github_url="https://github.com/example/dict",
            runtime_type="npx",
            start_command="npx start",
            env_variables=[{"key": "NODE_ENV", "value": "production"}],
        )
        db.session.add(server)
        db.session.commit()

        server_dict = server.to_dict()
        self.assertEqual(server_dict["name"], "Dict Test Server")
        self.assertEqual(server_dict["runtime_type"], "npx")
        self.assertIsInstance(server_dict["env_variables"], list)
        self.assertEqual(len(server_dict["env_variables"]), 1)
        self.assertEqual(server_dict["env_variables"][0]["key"], "NODE_ENV")

    def test_get_active_servers(self):
        """Test the get_active_servers function."""
        active_server = MCPServer(
            name="Active Server",
            github_url="https://github.com/example/active",
            runtime_type="docker",
            start_command="docker run active",
            is_active=True,
        )
        inactive_server = MCPServer(
            name="Inactive Server",
            github_url="https://github.com/example/inactive",
            runtime_type="docker",
            start_command="docker run inactive",
            is_active=False,
        )
        db.session.add_all([active_server, inactive_server])
        db.session.commit()

        active_servers = get_active_servers()
        self.assertEqual(len(active_servers), 1)
        self.assertEqual(active_servers[0].name, "Active Server")

    def test_auth_type_handling(self):
        """Test the get_auth_type and set_auth_type functions."""
        self.assertEqual(get_auth_type(), self.app.config["MCP_AUTH_TYPE"])

        ensure_server_status_exists()

        set_auth_type("oauth")
        self.assertEqual(get_auth_type(), "oauth")
        status = MCPServerStatus.query.first()
        self.assertEqual(status.auth_type, "oauth")

        set_auth_type("api_key")
        self.assertEqual(get_auth_type(), "api_key")

        with self.assertRaises(ValueError):
            set_auth_type("invalid_auth")


if __name__ == "__main__":
    unittest.main() 