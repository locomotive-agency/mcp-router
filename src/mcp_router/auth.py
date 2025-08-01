"""Simple authentication for MCP Router admin area"""

import bcrypt
from typing import Optional, Union
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.wrappers import Response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from flask_wtf import FlaskForm
from wtforms import PasswordField, validators
from mcp_router.config import Config
from mcp_router.logging_config import get_logger

logger = get_logger(__name__)


# Simple user class for Flask-Login
class User(UserMixin):
    """Simple user class with just an ID"""

    def __init__(self, user_id):
        self.id = user_id


# The single admin user
ADMIN_USER = User("admin")


class LoginForm(FlaskForm):
    """Login form with just a passcode field"""

    passcode = PasswordField(
        "Passcode",
        [
            validators.DataRequired(),
            validators.Length(min=8, message="Passcode must be at least 8 characters"),
        ],
    )


# Create auth blueprint
auth_bp = Blueprint("auth", __name__)

# Login manager instance
login_manager = LoginManager()


def init_auth(app) -> None:
    """Initialize authentication for the Flask app"""
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access the admin area."

    # Register blueprint
    app.register_blueprint(auth_bp)

    # Get passcode from config
    passcode = Config.ADMIN_PASSCODE
    if not passcode:
        raise ValueError("ADMIN_PASSCODE must be set in production environment")

    # Hash the passcode for storage
    app.config["ADMIN_PASSCODE_HASH"] = bcrypt.hashpw(passcode.encode("utf-8"), bcrypt.gensalt())


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user by ID - we only have one admin user"""
    if user_id == "admin":
        return ADMIN_USER
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> Union[str, Response]:
    """Login page - handles both GET and POST requests"""
    from flask import current_app

    form = LoginForm()

    if form.validate_on_submit():
        passcode = form.passcode.data
        passcode_hash = current_app.config.get("ADMIN_PASSCODE_HASH")

        # Check passcode
        if passcode_hash and bcrypt.checkpw(passcode.encode("utf-8"), passcode_hash):
            login_user(ADMIN_USER, remember=True)

            # Redirect to next page or index
            next_page = request.args.get("next")
            if not next_page or not next_page.startswith("/"):
                next_page = url_for("servers.index")

            flash("Logged in successfully!", "success")
            return redirect(next_page)
        else:
            flash("Invalid passcode. Please try again.", "error")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout() -> Response:
    """Logout current user and redirect to login page"""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
