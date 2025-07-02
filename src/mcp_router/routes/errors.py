"""Error handlers and utility routes"""

import logging
from typing import Tuple
from flask import render_template, Flask
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    """Register error handlers with the Flask app

    Args:
        app: Flask application instance
    """

    @app.errorhandler(404)
    def not_found(e: HTTPException) -> Tuple[str, int]:
        """Handle 404 errors

        Args:
            e: HTTPException instance

        Returns:
            Tuple of (rendered template, status code)
        """
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e: Exception) -> Tuple[str, int]:
        """Handle 500 errors

        Args:
            e: Exception instance

        Returns:
            Tuple of (rendered template, status code)
        """
        logger.error(f"Server error: {e}")
        return render_template("500.html"), 500

    @app.route("/favicon.ico")
    def favicon() -> Tuple[str, int]:
        """Return empty favicon to avoid 404 errors

        Returns:
            Tuple of (empty string, 204 status code)
        """
        return "", 204
