from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from mcp_anywhere.claude_analyzer import AsyncClaudeAnalyzer
from mcp_anywhere.container.manager import ContainerManager
from mcp_anywhere.database import MCPServer, MCPServerTool, get_async_session
from mcp_anywhere.database_utils import store_server_tools
from mcp_anywhere.logging_config import get_logger
from mcp_anywhere.web.forms import AnalyzeFormData, ServerFormData

logger = get_logger(__name__)
templates = Jinja2Templates(directory="src/mcp_anywhere/web/templates")


class CurrentUser:
    """Simple current user object for template context."""

    def __init__(self, user_id: str = None, username: str = None) -> None:
        self.user_id = user_id
        self.username = username
        self.is_authenticated = bool(user_id)


def get_current_user(request: Request) -> CurrentUser:
    """Get current user from session."""
    user_id = request.session.get("user_id")
    username = request.session.get("username")
    return CurrentUser(user_id, username)


def get_template_context(request: Request, **kwargs) -> dict:
    """Get base template context with current user and transport mode."""
    # Get transport mode from app state
    transport_mode = getattr(request.app.state, "transport_mode", "http")

    context = {
        "request": request,
        "current_user": get_current_user(request),
        "transport_mode": transport_mode,
        **kwargs,
    }
    return context


def get_mcp_manager(request: Request):
    """Get the MCP manager from the application state."""
    return getattr(request.app.state, "mcp_manager", None)


async def homepage(request: Request) -> HTMLResponse:
    """Renders the homepage, displaying a list of configured MCP servers."""
    try:
        async with get_async_session() as db_session:
            # Query all active servers with their tools
            stmt = (
                select(MCPServer)
                .options(selectinload(MCPServer.tools))
                .where(MCPServer.is_active)
                .order_by(MCPServer.name)
            )
            result = await db_session.execute(stmt)
            servers = result.scalars().all()

        return templates.TemplateResponse(
            request, "index.html", get_template_context(request, servers=servers)
        )

    except (RuntimeError, ValueError, ConnectionError) as e:
        # Log error and show empty server list
        logger.exception(f"Error loading servers: {e}")
        return templates.TemplateResponse(
            request,
            "index.html",
            get_template_context(request, servers=[], error=str(e)),
        )


async def server_detail(request: Request) -> HTMLResponse:
    """Show server details including tools."""
    server_id = request.path_params["server_id"]

    try:
        async with get_async_session() as db_session:
            # Get server
            stmt = select(MCPServer).where(MCPServer.id == server_id)
            result = await db_session.execute(stmt)
            server = result.scalar_one_or_none()

            if not server:
                return templates.TemplateResponse(
                    request,
                    "404.html",
                    {"message": f"Server '{server_id}' not found"},
                    status_code=404,
                )

            # Get tools for this server
            tools_stmt = (
                select(MCPServerTool)
                .where(MCPServerTool.server_id == server_id)
                .order_by(MCPServerTool.tool_name)
            )
            tools_result = await db_session.execute(tools_stmt)
            tools = tools_result.scalars().all()

        return templates.TemplateResponse(
            request,
            "servers/detail.html",
            get_template_context(request, server=server, tools=tools),
        )

    except (RuntimeError, ValueError, ConnectionError) as e:
        logger.exception(f"Error loading server details for {server_id}: {e}")
        return templates.TemplateResponse(
            request,
            "500.html",
            {"message": "Error loading server details"},
            status_code=500,
        )


async def delete_server(request: Request) -> RedirectResponse | HTMLResponse:
    """Delete a server and remove it from MCP manager."""
    server_id = request.path_params["server_id"]

    try:
        async with get_async_session() as db_session:
            # Get server first
            stmt = select(MCPServer).where(MCPServer.id == server_id)
            result = await db_session.execute(stmt)
            server = result.scalar_one_or_none()

            if not server:
                return templates.TemplateResponse(
                    request,
                    "404.html",
                    {"message": f"Server '{server_id}' not found"},
                    status_code=404,
                )

            server_name = server.name

            # Delete the server (cascade will handle tools)
            await db_session.delete(server)
            await db_session.commit()

            # Remove from MCP manager
            mcp_manager = get_mcp_manager(request)
            if mcp_manager:
                mcp_manager.remove_server(server_id)

            logger.info(f'Server "{server_name}" deleted successfully!')

        # Redirect to home page
        return RedirectResponse(url="/", status_code=302)

    except (RuntimeError, ValueError, ConnectionError, IntegrityError) as e:
        logger.exception(f"Error deleting server {server_id}: {e}")
        return templates.TemplateResponse(
            request, "500.html", {"message": "Error deleting server"}, status_code=500
        )


async def add_server_get(request: Request) -> HTMLResponse:
    """Display the add server form."""
    return templates.TemplateResponse(
        request, "servers/add.html", get_template_context(request)
    )


async def edit_server_get(request: Request) -> HTMLResponse:
    """Display the edit server form."""
    server_id = request.path_params["server_id"]

    try:
        async with get_async_session() as db_session:
            # Get server details
            stmt = select(MCPServer).where(MCPServer.id == server_id)
            result = await db_session.execute(stmt)
            server = result.scalar_one_or_none()

            if not server:
                return templates.TemplateResponse(
                    request,
                    "404.html",
                    get_template_context(
                        request, message=f"Server '{server_id}' not found"
                    ),
                    status_code=404,
                )

        return templates.TemplateResponse(
            request, "servers/edit.html", get_template_context(request, server=server)
        )

    except (RuntimeError, ValueError, ConnectionError) as e:
        logger.exception(f"Error loading server {server_id} for edit: {e}")
        return templates.TemplateResponse(
            request,
            "500.html",
            get_template_context(request, message="Error loading server"),
            status_code=500,
        )


async def edit_server_post(request: Request) -> HTMLResponse:
    """Handle edit server form submission."""
    server_id = request.path_params["server_id"]
    form_data = await request.form()

    try:
        # Handle environment variables from form (new indexed format)
        server_data = await create_server_post_form_data(form_data)

        # Update server in database
        async with get_async_session() as db_session:
            stmt = select(MCPServer).where(MCPServer.id == server_id)
            result = await db_session.execute(stmt)
            server = result.scalar_one_or_none()

            if not server:
                return templates.TemplateResponse(
                    request,
                    "404.html",
                    {"message": f"Server '{server_id}' not found"},
                    status_code=404,
                )

            # Update server fields
            server.name = server_data.name
            server.github_url = server_data.github_url
            server.description = server_data.description
            server.runtime_type = server_data.runtime_type
            server.install_command = server_data.install_command or ""
            server.start_command = server_data.start_command
            server.env_variables = server_data.env_variables

            await db_session.commit()
            logger.info(f'Server "{server.name}" updated successfully!')

            # Rebuild the server after configuration changes
            try:
                # Update build status
                server.build_status = "building"
                await db_session.commit()

                # Build the Docker image
                container_manager = ContainerManager()
                image_tag = container_manager.build_server_image(server)

                # Update server with success
                server.build_status = "built"
                server.image_tag = image_tag
                server.build_error = None
                await db_session.commit()

                # Re-add server to MCP manager and get updated tools
                mcp_manager = get_mcp_manager(request)
                if mcp_manager:
                    # Remove old server first
                    mcp_manager.remove_server(server.id)
                    # Clean up any existing container before re-adding
                    container_name = container_manager._get_container_name(server.id)
                    container_manager._cleanup_existing_container(container_name)
                    # Add updated server and discover tools
                    discovered_tools = await mcp_manager.add_server(server)
                    await store_server_tools(db_session, server, discovered_tools)

                logger.info(f'Server "{server.name}" rebuilt successfully after edit!')

            except (RuntimeError, ValueError, ConnectionError, OSError) as e:
                logger.exception(f"Failed to rebuild image for {server.name}: {e}")
                server.build_status = "failed"
                server.build_error = str(e)
                await db_session.commit()

        # Redirect to server detail page (HTMX compatible)
        if request.headers.get("HX-Request"):
            response = HTMLResponse("", status_code=200)
            response.headers["HX-Redirect"] = f"/servers/{server_id}"
            return response
        else:
            return RedirectResponse(url=f"/servers/{server_id}", status_code=302)

    except ValidationError as e:
        errors = {}
        for error in e.errors():
            field = error["loc"][0]
            errors[field] = [error["msg"]]

        # Re-fetch server for form
        async with get_async_session() as db_session:
            stmt = select(MCPServer).where(MCPServer.id == server_id)
            result = await db_session.execute(stmt)
            server = result.scalar_one_or_none()

        return templates.TemplateResponse(
            request,
            "servers/edit.html",
            get_template_context(request, server=server, errors=errors),
        )

    except (
        RuntimeError,
        ValueError,
        ConnectionError,
        ValidationError,
        IntegrityError,
    ) as e:
        logger.exception(f"Error updating server {server_id}: {e}")
        return templates.TemplateResponse(
            request,
            "500.html",
            get_template_context(request, message="Error updating server"),
            status_code=500,
        )


async def create_server_post_form_data(form_data: FormData) -> ServerFormData:
    """Create ServerFormData from form data, handling both old and new formats."""
    env_variables = []

    # First try the old format for backward compatibility
    env_keys = form_data.getlist("env_keys[]")
    for key in env_keys:
        value = form_data.get(f"env_value_{key}", "")
        description = form_data.get(f"env_desc_{key}", "")
        if value:  # Only include env vars with values
            env_variables.append(
                {"key": key, "value": value, "description": description}
            )
    # New indexed format from analysis result template
    i = 0
    while True:
        key = form_data.get(f"env_key_{i}")
        if key is None:
            break
        value = form_data.get(f"env_value_{i}", "")
        description = form_data.get(f"env_desc_{i}", "")
        required = form_data.get(f"env_required_{i}", "false").lower() == "true"

        if key.strip():  # Only include env vars with non-empty keys
            env_variables.append(
                {
                    "key": key.strip(),
                    "value": value,
                    "description": description,
                    "required": required,
                }
            )
        i += 1
    # Validate form data
    server_data = ServerFormData(
        name=form_data.get("name", ""),
        github_url=form_data.get("github_url", ""),
        description=form_data.get("description", ""),
        runtime_type=form_data.get("runtime_type", ""),
        install_command=form_data.get("install_command", ""),
        start_command=form_data.get("start_command", ""),
        env_variables=env_variables,
    )
    return server_data


async def toggle_tool(request: Request) -> HTMLResponse:
    """Toggle tool enabled/disabled status via HTMX."""
    server_id = request.path_params["server_id"]
    tool_id = request.path_params["tool_id"]

    try:
        async with get_async_session() as db_session:
            # Get the tool
            stmt = select(MCPServerTool).where(
                MCPServerTool.id == tool_id, MCPServerTool.server_id == server_id
            )
            result = await db_session.execute(stmt)
            tool = result.scalar_one_or_none()

            if not tool:
                return templates.TemplateResponse(
                    request,
                    "404.html",
                    get_template_context(
                        request, message=f"Tool '{tool_id}' not found"
                    ),
                    status_code=404,
                )

            # Toggle the enabled status
            tool.is_enabled = not tool.is_enabled
            await db_session.commit()

            logger.info(
                f'Tool "{tool.tool_name}" {"enabled" if tool.is_enabled else "disabled"}'
            )

        # Return just the updated toggle switch HTML for HTMX
        return templates.TemplateResponse(
            request,
            "partials/tool_toggle.html",
            get_template_context(request, tool=tool, server_id=server_id),
        )

    except (RuntimeError, ValueError, ConnectionError, IntegrityError) as e:
        logger.exception(f"Error toggling tool {tool_id}: {e}")
        return templates.TemplateResponse(
            request,
            "500.html",
            get_template_context(request, message="Error toggling tool"),
            status_code=500,
        )


async def handle_claude_connection_error(
    request: Request, github_url: str, error: ConnectionError
) -> HTMLResponse:
    """Handle Claude analysis connection failures with fallback."""
    logger.warning(f"Claude analysis failed for {github_url}: {error}")

    # Fallback to basic analysis if Claude fails
    analysis = {
        "name": "analyzed-server",
        "description": "Claude analysis unavailable - please fill manually",
        "runtime_type": "docker",
        "install_command": "",
        "start_command": "echo 'placeholder'",
    }

    warning_msg = "Repository analysis failed. Please fill out the form manually."

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/analysis_result.html",
            get_template_context(
                request,
                github_url=github_url,
                analysis=analysis,
                warning=warning_msg,
            ),
        )
    else:
        return templates.TemplateResponse(
            request,
            "servers/add.html",
            get_template_context(
                request,
                github_url=github_url,
                analysis=analysis,
                warning=warning_msg,
            ),
        )


async def handle_claude_config_error(
    request: Request, github_url: str, error: ValueError
) -> HTMLResponse:
    """Handle Claude analyzer configuration errors."""
    logger.error(f"Claude analyzer configuration error: {error}")
    error_msg = f"Repository analysis is not configured: {str(error)}. Please check your ANTHROPIC_API_KEY."

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/analysis_result.html",
            get_template_context(request, github_url=github_url, error=error_msg),
        )
    else:
        return templates.TemplateResponse(
            request,
            "servers/add.html",
            get_template_context(request, github_url=github_url, error=error_msg),
        )


async def handle_claude_unexpected_error(
    request: Request, github_url: str, error: Exception
) -> HTMLResponse:
    """Handle unexpected errors during Claude analysis."""
    logger.error(f"Unexpected error during analysis: {error}")
    error_msg = f"Analysis failed: {str(error)}"

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/analysis_result.html",
            get_template_context(request, github_url=github_url, error=error_msg),
        )
    else:
        return templates.TemplateResponse(
            request,
            "servers/add.html",
            get_template_context(request, github_url=github_url, error=error_msg),
        )


async def handle_analyze_validation_error(
    request: Request, form_data, error: ValidationError
) -> HTMLResponse:
    """Handle form validation errors during analysis."""
    logger.error(f"Form validation error: {error}")
    errors = {}
    for err in error.errors():
        field = err["loc"][0]
        errors[field] = [err["msg"]]

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/analysis_result.html",
            get_template_context(
                request,
                github_url=form_data.get("github_url", ""),
                errors=errors,
            ),
        )
    else:
        return templates.TemplateResponse(
            request,
            "servers/add.html",
            get_template_context(
                request,
                github_url=form_data.get("github_url", ""),
                errors=errors,
            ),
        )


async def handle_analyze_general_error(
    request: Request, form_data, error: Exception
) -> HTMLResponse:
    """Handle general errors during analysis."""
    logger.error(f"Unexpected error in analyze handler: {error}")
    error_msg = f"Unexpected error: {str(error)}"

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/analysis_result.html",
            get_template_context(
                request,
                github_url=form_data.get("github_url", ""),
                error=error_msg,
            ),
        )
    else:
        return templates.TemplateResponse(
            request,
            "servers/add.html",
            get_template_context(
                request,
                github_url=form_data.get("github_url", ""),
                error=error_msg,
            ),
        )


async def handle_analyze_repository(request: Request, form_data) -> HTMLResponse:
    """Handle repository analysis request."""
    logger.info(f"Analyze button clicked for URL: {form_data.get('github_url', '')}")
    try:
        analyze_data = AnalyzeFormData(github_url=form_data.get("github_url", ""))
        logger.info("Form data validated successfully")

        # Use the real Claude analyzer
        try:
            logger.info("Initializing AsyncClaudeAnalyzer...")
            analyzer = AsyncClaudeAnalyzer()
            logger.info(f"Starting repository analysis for: {analyze_data.github_url}")
            analysis = await analyzer.analyze_repository(analyze_data.github_url)
            logger.info("Analysis completed successfully")

            # Check if this is an HTMX request
            if request.headers.get("HX-Request"):
                return templates.TemplateResponse(
                    request,
                    "partials/analysis_result.html",
                    get_template_context(
                        request,
                        github_url=analyze_data.github_url,
                        analysis=analysis,
                    ),
                )
            else:
                return templates.TemplateResponse(
                    request,
                    "servers/add.html",
                    get_template_context(
                        request,
                        github_url=analyze_data.github_url,
                        analysis=analysis,
                    ),
                )

        except ConnectionError as e:
            return await handle_claude_connection_error(
                request=request, github_url=analyze_data.github_url, error=e
            )

        except ValueError as e:
            return await handle_claude_config_error(
                request=request, github_url=analyze_data.github_url, error=e
            )

        except (RuntimeError, ValueError, ConnectionError, OSError) as e:
            return await handle_claude_unexpected_error(
                request=request, github_url=analyze_data.github_url, error=e
            )

    except ValidationError as e:
        return await handle_analyze_validation_error(
            request=request, form_data=form_data, error=e
        )

    except (RuntimeError, ValueError, ConnectionError, ValidationError) as e:
        return await handle_analyze_general_error(
            request=request, form_data=form_data, error=e
        )


async def handle_save_server(request: Request, form_data) -> HTMLResponse:
    """Handle server save request."""
    try:
        # Handle environment variables from form (new indexed format)
        server_data = await create_server_post_form_data(form_data)

        # Create server in database
        async with get_async_session() as db_session:
            server = MCPServer(
                name=server_data.name,
                github_url=server_data.github_url,
                description=server_data.description,
                runtime_type=server_data.runtime_type,
                install_command=server_data.install_command or "",
                start_command=server_data.start_command,
                env_variables=server_data.env_variables,
            )

            db_session.add(server)
            await db_session.commit()
            await db_session.refresh(server)  # Get the generated ID

            try:
                # Update build status
                server.build_status = "building"
                await db_session.commit()

                # Build the Docker image
                container_manager = ContainerManager()
                image_tag = container_manager.build_server_image(server)

                # Update server with success
                server.build_status = "built"
                server.image_tag = image_tag
                server.build_error = None
                await db_session.commit()

                # Add server to MCP manager and get tools
                mcp_manager = get_mcp_manager(request)
                if mcp_manager:
                    # Clean up any existing container before adding
                    container_name = container_manager._get_container_name(server.id)
                    container_manager._cleanup_existing_container(container_name)
                    discovered_tools = await mcp_manager.add_server(server)
                    await store_server_tools(db_session, server, discovered_tools)

                logger.info(f'Server "{server.name}" added and built successfully!')

            except (RuntimeError, ValueError, ConnectionError, OSError) as e:
                logger.exception(f"Failed to build image for {server.name}: {e}")
                server.build_status = "failed"
                server.build_error = str(e)
                await db_session.commit()

            # Redirect to home page (HTMX compatible)
            if request.headers.get("HX-Request"):
                response = HTMLResponse("", status_code=200)
                response.headers["HX-Redirect"] = "/"
                return response
            else:
                return RedirectResponse(url="/", status_code=302)

    except ValidationError as e:
        errors = {}
        for error in e.errors():
            field = error["loc"][0]
            errors[field] = [error["msg"]]

        return templates.TemplateResponse(
            request,
            "servers/add.html",
            get_template_context(request, form_data=form_data, errors=errors),
        )

    except IntegrityError:
        return templates.TemplateResponse(
            request,
            "servers/add.html",
            get_template_context(
                request,
                form_data=form_data,
                error="A server with this name already exists.",
            ),
        )

    except (
        RuntimeError,
        ValueError,
        ConnectionError,
        ValidationError,
        IntegrityError,
    ) as e:
        logger.exception(f"Error saving server: {e}")
        return templates.TemplateResponse(
            request,
            "servers/add.html",
            get_template_context(
                request,
                form_data=form_data,
                error="Error saving server. Please try again.",
            ),
        )


async def add_server_post(request: Request) -> HTMLResponse:
    """Handle add server form submission."""
    form_data = await request.form()

    # Handle analyze button
    if "analyze" in form_data:
        return await handle_analyze_repository(request, form_data)

    # Handle save button
    elif "save" in form_data:
        return await handle_save_server(request, form_data)

    # Invalid form submission
    return templates.TemplateResponse(
        request, "servers/add.html", get_template_context(request, form_data=form_data)
    )


async def add_server(request: Request) -> HTMLResponse:
    """Handle both GET and POST for /servers/add."""
    if request.method == "GET":
        return await add_server_get(request)
    else:
        return await add_server_post(request)


async def edit_server(request: Request):
    """Handle both GET and POST for /servers/{server_id}/edit."""
    if request.method == "GET":
        return await edit_server_get(request)
    else:
        return await edit_server_post(request)


async def favicon(request: Request):
    """Handle favicon.ico requests with a 204 No Content response to silence 404s."""
    return Response(status_code=204)


routes = [
    Route("/", endpoint=homepage),
    Route("/favicon.ico", endpoint=favicon, methods=["GET"]),
    Route("/servers/add", endpoint=add_server, methods=["GET", "POST"]),
    Route("/servers/{server_id}", endpoint=server_detail, methods=["GET"]),
    Route("/servers/{server_id}/edit", endpoint=edit_server, methods=["GET", "POST"]),
    Route(
        "/servers/{server_id}/tools/{tool_id}/toggle",
        endpoint=toggle_tool,
        methods=["POST", "GET"],
    ),
    Route("/servers/{server_id}/delete", endpoint=delete_server, methods=["POST"]),
]
