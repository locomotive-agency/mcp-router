
import unittest
from flask import Flask
from mcp_router.app import app as flask_app  # Import the app instance
from mcp_router.config import TestingConfig


class TestApp(unittest.TestCase):
    """Test cases for the Flask application setup."""

    def setUp(self):
        """Set up the test client and application context."""
        self.app = flask_app
        self.app.config.from_object(TestingConfig)
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        """Tear down the application context."""
        self.app_context.pop()

    def test_app_creation(self):
        """Test if the Flask application is created and configured for testing."""
        self.assertIsInstance(self.app, Flask)
        self.assertTrue(self.app.config["TESTING"])
        self.assertFalse(self.app.config["WTF_CSRF_ENABLED"])

    def test_blueprint_registration(self):
        """Test if all required blueprints are registered."""
        registered_blueprints = self.app.blueprints.keys()
        self.assertIn("servers", registered_blueprints)
        self.assertIn("mcp", registered_blueprints)
        self.assertIn("config", registered_blueprints)
        self.assertIn("oauth", registered_blueprints)

    def test_proxy_fix_middleware(self):
        """Test that the ProxyFix middleware is applied."""
        # The wsgi_app attribute is wrapped by ProxyFix
        self.assertTrue(hasattr(self.app.wsgi_app, "app"))
        self.assertEqual(
            self.app.wsgi_app.__class__.__name__, "ProxyFix"
        )




if __name__ == "__main__":
    unittest.main() 