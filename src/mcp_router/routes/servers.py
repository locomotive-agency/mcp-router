"""Server management routes for MCP Router"""

import logging
from typing import Union, Tuple
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    make_response,
    Response,
)
from flask_login import login_required
from sqlalchemy.exc import IntegrityError
from mcp_router.models import db, MCPServer
from mcp_router.forms import ServerForm, AnalyzeForm
from mcp_router.container_manager import ContainerManager
from mcp_router.claude_analyzer import ClaudeAnalyzer
from flask import current_app

logger = logging.getLogger(__name__)

# Create blueprint
servers_bp = Blueprint("servers", __name__)


@servers_bp.route("/")
@login_required
def index() -> str:
    """Dashboard showing all servers

    Returns:
        Rendered index template with server list
    """
    try:
        servers = MCPServer.query.filter_by(is_active=True).all()
        return render_template("index.html", servers=servers)
    except Exception as e:
        logger.error(f"Error loading servers: {e}")
        flash("Error loading servers. Please try again.", "error")
        return render_template("index.html", servers=[])


@servers_bp.route("/servers/add", methods=["GET", "POST"])
@login_required
def add_server() -> Union[str, Response]:
    """Add new server with GitHub analysis

    Returns:
        Rendered template or redirect response
    """
    if request.method == "POST":
        # Handle analyze button
        if "analyze" in request.form:
            analyze_form = AnalyzeForm()
            if analyze_form.validate_on_submit():
                github_url = analyze_form.github_url.data
                try:
                    # Use the real ClaudeAnalyzer
                    analyzer = ClaudeAnalyzer()
                    analysis = analyzer.analyze_repository(github_url)

                    # For HTMX requests, use a partial template
                    if request.headers.get("HX-Request"):
                        return render_template(
                            "servers/add_form.html", github_url=github_url, analysis=analysis
                        )
                    else:
                        return render_template(
                            "servers/add.html", github_url=github_url, analysis=analysis
                        )
                except Exception as e:
                    logger.error(f"Error analyzing repository '{github_url}': {e}")

                    # For HTMX requests, use a partial template
                    if request.headers.get("HX-Request"):
                        return render_template(
                            "servers/add_form.html", github_url=github_url, error=str(e)
                        )
                    else:
                        flash(f"Analysis failed: {e}", "error")
                        return render_template(
                            "servers/add.html", github_url=github_url, error=str(e)
                        )
            else:
                flash("Invalid GitHub URL format.", "error")

        # Handle save button
        elif "save" in request.form:
            server_form = ServerForm()
            if server_form.validate_on_submit():
                try:
                    server = MCPServer(
                        name=server_form.name.data,
                        github_url=server_form.github_url.data,
                        description=server_form.description.data,
                        runtime_type=server_form.runtime_type.data,
                        install_command=server_form.install_command.data or "",
                        start_command=server_form.start_command.data,
                    )

                    # Add environment variables
                    env_vars = []
                    for key in request.form.getlist("env_keys[]"):
                        if key:
                            env_vars.append(
                                {
                                    "key": key.strip(),
                                    "value": request.form.get(f"env_value_{key}", "").strip(),
                                    "description": request.form.get(f"env_desc_{key}", "").strip(),
                                }
                            )
                    server.env_variables = env_vars

                    db.session.add(server)
                    db.session.commit()

                    flash(f'Server "{server.name}" added successfully!', "success")

                    # Handle HTMX requests with HX-Redirect to avoid duplicate headers
                    if request.headers.get("HX-Request"):
                        response = make_response("", 204)
                        response.headers["HX-Redirect"] = url_for("servers.index")
                        return response
                    else:
                        return redirect(url_for("servers.index"))

                except IntegrityError:
                    db.session.rollback()
                    flash("A server with this name already exists.", "error")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Error saving server: {e}")
                    flash("Error saving server. Please try again.", "error")

    return render_template("servers/add.html")


@servers_bp.route("/servers/<server_id>")
@login_required
def server_detail(server_id: str) -> str:
    """Show server details

    Args:
        server_id: ID of the server to display

    Returns:
        Rendered server detail template
    """
    server = MCPServer.query.get_or_404(server_id)
    return render_template("servers/detail.html", server=server)


@servers_bp.route("/servers/<server_id>/edit", methods=["GET", "POST"])
@login_required
def edit_server(server_id: str) -> Union[str, Response]:
    """Edit server configuration

    Args:
        server_id: ID of the server to edit

    Returns:
        Rendered edit template or redirect response
    """
    server = MCPServer.query.get_or_404(server_id)

    if request.method == "POST":
        form = ServerForm()
        if form.validate_on_submit():
            try:
                server.name = form.name.data
                server.github_url = form.github_url.data
                server.description = form.description.data
                server.runtime_type = form.runtime_type.data
                server.install_command = form.install_command.data or ""
                server.start_command = form.start_command.data

                # Update environment variables
                env_vars = []
                for key in request.form.getlist("env_keys[]"):
                    if key:
                        env_vars.append(
                            {
                                "key": key.strip(),
                                "value": request.form.get(f"env_value_{key}", "").strip(),
                                "description": request.form.get(f"env_desc_{key}", "").strip(),
                            }
                        )
                server.env_variables = env_vars

                db.session.commit()
                flash("Server updated successfully!", "success")
                return redirect(url_for("servers.server_detail", server_id=server.id))

            except IntegrityError:
                db.session.rollback()
                flash("A server with this name already exists.", "error")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating server: {e}")
                flash("Error updating server. Please try again.", "error")

    # Pre-populate form
    form = ServerForm(obj=server)
    return render_template("servers/edit.html", server=server, form=form)


@servers_bp.route("/servers/<server_id>/delete", methods=["POST"])
@login_required
def delete_server(server_id: str) -> Response:
    """Delete a server

    Args:
        server_id: ID of the server to delete

    Returns:
        Redirect response to index
    """
    server = MCPServer.query.get_or_404(server_id)

    try:
        db.session.delete(server)
        db.session.commit()
        flash(f'Server "{server.name}" deleted successfully!', "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting server: {e}")
        flash("Error deleting server. Please try again.", "error")

    return redirect(url_for("servers.index"))


@servers_bp.route("/servers/<server_id>/toggle", methods=["POST"])
@login_required
def toggle_server(server_id: str) -> Union[Response, Tuple[str, int]]:
    """Toggle server active status

    Args:
        server_id: ID of the server to toggle

    Returns:
        Response for HTMX or redirect to server detail
    """
    server = MCPServer.query.get_or_404(server_id)

    try:
        server.is_active = not server.is_active
        db.session.commit()

        status = "activated" if server.is_active else "deactivated"
        flash(f'Server "{server.name}" {status}!', "success")

        # For HTMX request, redirect to refresh the page
        if request.headers.get("HX-Request"):
            response = make_response("", 204)
            response.headers["HX-Refresh"] = "true"
            return response

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling server: {e}")
        flash("Error updating server status.", "error")

    return redirect(url_for("servers.server_detail", server_id=server.id))


@servers_bp.route("/api/servers/<server_id>/test", methods=["POST"])
@login_required
def test_server(server_id: str) -> str:
    """
    Test server connection by spawning a container (htmx endpoint).

    Args:
        server_id: ID of the server to test

    Returns:
        HTML string with test result
    """


    manager = ContainerManager(current_app)
    result = manager.test_server(server_id)

    if result.get("status") == "success":
        return f'<div class="text-green-600">✓ Server test successful! Exit code: {result["exit_code"]}</div>'
    else:
        return f'<div class="text-red-600">✗ {result["message"]} ({result.get("stderr", "No details")})</div>'
