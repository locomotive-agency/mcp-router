"""Main Flask application for MCP Router"""

import logging
from typing import Dict, Any
from flask import Flask
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from mcp_router.config import get_config
from mcp_router.routes import servers_bp, mcp_bp, config_bp, register_error_handlers
from mcp_router.routes.mcp import register_csrf_exemptions
from mcp_router.models import init_db
from mcp_router.auth import init_auth
from mcp_router.server_manager import init_server_manager
from mcp_router.mcp_oauth import create_oauth_blueprint
from werkzeug.middleware.proxy_fix import ProxyFix



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(get_config())
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Initialize CORS
CORS(app, resources={
    r"/mcp": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "mcp-protocol-version"],
        "expose_headers": ["Content-Type", "Authorization"]
    },
    r"/mcp/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "mcp-protocol-version"],
        "expose_headers": ["Content-Type", "Authorization"]
    },
    r"/.well-known/*": {
        "origins": "*",
        "methods": ["GET", "OPTIONS"],
        "allow_headers": ["Content-Type", "mcp-protocol-version"],
        "expose_headers": ["Content-Type"]
    },
    r"/oauth/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "mcp-protocol-version"],
        "expose_headers": ["Content-Type", "Authorization"]
    }
})

# Initialize extensions
csrf = CSRFProtect(app)
init_db(app)
init_auth(app)  # Initialize authentication

# Initialize server manager with app context
app.server_manager = init_server_manager(app)

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
    """Add utility functions to templates

    Returns:
        Dictionary of utility functions available in templates
    """
    return {
        "len": len,
        "str": str,
    }


# Application is run from web.py
