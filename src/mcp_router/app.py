"""Main Flask application for MCP Router"""

from typing import Dict, Any
from flask import Flask
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from mcp_router.config import get_config
from mcp_router.routes import servers_bp, mcp_bp, config_bp, register_error_handlers
from mcp_router.routes.mcp import register_csrf_exemptions
from mcp_router.models import init_db
from mcp_router.auth import init_auth
from threading import Thread
from mcp_router.logging_config import get_logger
from mcp_router.config import Config
from mcp_router.mcp_oauth import create_oauth_blueprint
from werkzeug.middleware.proxy_fix import ProxyFix


logger = get_logger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(get_config())
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Initialize CORS
CORS(
    app,
    resources={
        r"/mcp": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "mcp-protocol-version"],
            "expose_headers": ["Content-Type", "Authorization"],
        },
        r"/mcp/*": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "mcp-protocol-version"],
            "expose_headers": ["Content-Type", "Authorization"],
        },
        r"/.well-known/*": {
            "origins": "*",
            "methods": ["GET", "OPTIONS"],
            "allow_headers": ["Content-Type", "mcp-protocol-version"],
            "expose_headers": ["Content-Type"],
        },
        r"/oauth/*": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "mcp-protocol-version"],
            "expose_headers": ["Content-Type", "Authorization"],
        },
    },
)

# Initialize extensions
csrf = CSRFProtect(app)
init_db(app)
init_auth(app)  # Initialize authentication

# Register OAuth blueprint for MCP server authentication
oauth_bp = create_oauth_blueprint()
app.register_blueprint(oauth_bp)

# Exempt OAuth endpoints from CSRF protection
csrf.exempt(oauth_bp)

app.register_blueprint(servers_bp)
app.register_blueprint(mcp_bp)
app.register_blueprint(config_bp)

# Register CSRF exemptions for MCP routes
register_csrf_exemptions(csrf)

# Register error handlers
register_error_handlers(app)


# Register context processor
@app.context_processor
def utility_processor() -> Dict[str, Any]:
    """Add utility functions to templates"""
    return {
        "len": len,
        "str": str,
    }


def run_web_ui_in_background():
    """
    Run the Flask web UI in a background thread.
    This is used in STDIO mode to provide a web interface for managing
    servers while the main thread handles the stdio transport.
    """

    def run():
        # The database is already initialized by the main application context
        # No need to re-initialize here
        app.run(
            host="0.0.0.0",  # Always bind to all interfaces in background mode
            port=Config.FLASK_PORT,
            debug=False,
            use_reloader=False,
        )

    thread = Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"Web UI is running in the background on http://127.0.0.1:{Config.FLASK_PORT}")


# Application entry point is __main__.py which selects HTTP or STDIO transport mode
