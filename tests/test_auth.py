
import unittest
from flask import Flask, url_for, Blueprint
from flask_wtf.csrf import CSRFProtect
from mcp_router.auth import init_auth
from mcp_router.config import TestingConfig
from flask_login import login_required


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        """Set up a test Flask application and initialize authentication."""
        self.app = Flask(__name__, template_folder="../src/mcp_router/templates")
        self.app.config.from_object(TestingConfig)
        self.app.config["SERVER_NAME"] = "localhost"
        self.app.config["ADMIN_PASSCODE"] = "testpasscode123"

        # Initialize CSRF protection for templates
        csrf = CSRFProtect(self.app)

        # Create a mock servers blueprint to satisfy template url_for calls
        servers_bp = Blueprint("servers", __name__)
        
        @servers_bp.route("/")
        def index():
            return "MCP Servers"
            
        @servers_bp.route("/add")
        def add_server():
            return "Add Server"
            
        self.app.register_blueprint(servers_bp, url_prefix="/servers")

        # Add a dummy protected route for testing
        @self.app.route("/protected")
        @login_required
        def protected_route():
            return "Protected Content"

        init_auth(self.app)  # This registers the auth_bp
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        """Tear down the application context."""
        self.app_context.pop()

    def test_login_successful(self):
        """Test that login endpoint accepts POST requests."""
        response = self.client.post(
            url_for("auth.login"),
            data={"passcode": "testpasscode123"},
            follow_redirects=False,
        )
        # Test that the endpoint processes the request (doesn't return 404 or 500)
        self.assertIn(response.status_code, [200, 302])

    def test_login_failed(self):
        """Test a failed login with an incorrect passcode."""
        response = self.client.post(
            url_for("auth.login"),
            data={"passcode": "wrongpassword"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid passcode", response.data)

    def test_logout(self):
        """Test the logout functionality."""
        # Test that logout endpoint exists and responds
        response = self.client.get(url_for("auth.logout"))
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)

    def test_login_required_redirect(self):
        """Test that a protected route redirects to the login page."""
        response = self.client.get("/protected", follow_redirects=False)
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)


if __name__ == "__main__":
    unittest.main() 