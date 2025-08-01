
import os
import unittest
from unittest.mock import patch
from mcp_router.config import (
    get_config,
    Config,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
)


class TestConfig(unittest.TestCase):
    """Test cases for the configuration setup."""

    def test_get_config_default(self):
        """Test get_config default behavior."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_config()
            self.assertEqual(config.__name__, "DevelopmentConfig")

    @patch.dict(os.environ, {"FLASK_ENV": "production"})
    def test_get_config_production(self):
        """Test get_config returns ProductionConfig for production environment."""
        config = get_config()
        self.assertEqual(config.__name__, "ProductionConfig")

    @patch.dict(os.environ, {"FLASK_ENV": "testing"})
    def test_get_config_testing(self):
        """Test get_config returns TestingConfig for testing environment."""
        config = get_config()
        self.assertEqual(config.__name__, "TestingConfig")
        self.assertTrue(config.TESTING)
        self.assertEqual(config.SQLALCHEMY_DATABASE_URI, "sqlite:///:memory:")

    def test_config_has_auth_settings(self):
        """Test that config classes have auth-related settings."""
        config_class = get_config()
        self.assertTrue(hasattr(config_class, 'MCP_AUTH_TYPE'))
        self.assertTrue(hasattr(config_class, 'MCP_API_KEY'))
        self.assertIn(config_class.MCP_AUTH_TYPE, ['oauth', 'api_key'])

    def test_config_auth_type_values(self):
        """Test that auth type is limited to valid values."""
        self.assertIn(Config.MCP_AUTH_TYPE, ['oauth', 'api_key'])
        self.assertIsInstance(Config.FLASK_PORT, int)
        self.assertIsInstance(Config.WTF_CSRF_ENABLED, bool)

    def test_base_config_defaults(self):
        """Test the default values in the base Config class."""
        with patch.dict(os.environ, {}, clear=True):
            # Test the actual default values from the environment
            self.assertEqual(Config.MCP_AUTH_TYPE, "oauth")  # Default is oauth
            self.assertEqual(Config.FLASK_PORT, 8000)
            self.assertFalse(Config.DEBUG)
            self.assertTrue(Config.WTF_CSRF_ENABLED)


if __name__ == "__main__":
    unittest.main() 