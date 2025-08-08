"""OAuth routes using MCP SDK's auth module.
Provides all required endpoints including .well-known discovery.
"""

from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from mcp_anywhere.auth.models import User
from mcp_anywhere.auth.provider import MCPAnywhereAuthProvider
from mcp_anywhere.config import Config
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)

# Templates for login/consent pages
from pathlib import Path

# Get the correct template directory path
template_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(template_dir))


async def login_page(request: Request) -> HTMLResponse:
    """Render the login page."""
    error = request.query_params.get("error")
    next_url = request.query_params.get("next", "")
    return templates.TemplateResponse(
        request, "auth/login.html", {"error": error, "next_url": next_url}
    )


async def handle_login(request: Request) -> RedirectResponse:
    """Process login form submission."""
    form = await request.form()
    username = form.get("username")
    password = form.get("password")

    # Get next URL from form data first, then query params as fallback
    next_url = form.get("next") or request.query_params.get("next", "/")

    # Get database session
    async with request.app.state.get_async_session() as session:
        stmt = select(User).where(User.username == username)
        user = await session.scalar(stmt)

        if user and user.check_password(password):
            # Set session
            request.session["user_id"] = user.id
            request.session["username"] = user.username

            # Redirect to original OAuth request or specified next URL
            logger.info(
                f"User {username} logged in successfully, redirecting to: {next_url}"
            )
            return RedirectResponse(url=next_url, status_code=302)

    # Login failed - preserve next URL in error redirect
    error_url = "/auth/login?error=invalid_credentials"
    if next_url != "/":
        error_url += f"&next={next_url}"
    return RedirectResponse(url=error_url, status_code=302)


async def consent_page(request: Request) -> HTMLResponse:
    """Render the consent page with CSRF protection."""
    # Get state parameter from URL
    state = request.query_params.get("state")
    if not state:
        logger.warning("Consent page accessed without state parameter")
        return RedirectResponse(url="/", status_code=302)

    # Retrieve OAuth request from provider using state
    oauth_provider = getattr(request.app.state, "oauth_provider", None)
    if not oauth_provider:
        logger.error("OAuth provider not available")
        return RedirectResponse(url="/", status_code=302)

    oauth_request = oauth_provider.oauth_requests.get(state)
    if not oauth_request:
        logger.warning(f"No OAuth request found for state: {state}")
        return RedirectResponse(url="/", status_code=302)

    # Check if user is authenticated (admin session)
    user_id = request.session.get("user_id")
    username = request.session.get("username")

    if not user_id:
        # User not authenticated, redirect to login with return URL
        login_url = f"/auth/login?next={request.url}"
        logger.info(f"User not authenticated, redirecting to login: {login_url}")
        return RedirectResponse(url=login_url, status_code=302)

    # User is authenticated, show consent page
    # Store OAuth request in session for form processing (add user_id)
    oauth_request["user_id"] = user_id  # Add authenticated user ID
    request.session["oauth_request"] = oauth_request
    request.session["oauth_state"] = state

    # No CSRF token needed - using SameSite strict cookies for protection

    # Handle scopes safely - ensure it's always a list
    scopes = oauth_request.get("scopes", [])
    if scopes is None:
        scopes = []
    elif not isinstance(scopes, list):
        # If it's a string, split it
        scopes = str(scopes).split() if scopes else []

    return templates.TemplateResponse(
        request,
        "auth/consent.html",
        {
            "client_id": oauth_request.get("client_id"),
            "scope": " ".join(scopes),
            "username": username,
        },
    )


async def handle_consent(request: Request) -> RedirectResponse:
    """Process consent form submission. CSRF protection via SameSite strict cookies."""
    form = await request.form()
    action = form.get("action", "deny")

    oauth_request = request.session.get("oauth_request", {})
    if not oauth_request:
        return RedirectResponse(url="/", status_code=302)

    provider = request.app.state.oauth_provider

    if action == "allow":
        # Generate authorization code
        try:
            code = await provider.create_authorization_code(
                request=request, **oauth_request
            )

            # Build redirect URL
            redirect_uri = oauth_request["redirect_uri"]
            params = f"code={code}"
            if oauth_request.get("state"):
                params += f"&state={oauth_request['state']}"

            redirect_url = f"{redirect_uri}?{params}"

            logger.info(
                f"User {oauth_request.get('user_id')} approved OAuth request for "
                f"client {oauth_request.get('client_id')}, redirecting with code"
            )
        except Exception as e:
            logger.exception(f"Failed to create authorization code: {e}")
            # Redirect with error
            redirect_uri = oauth_request["redirect_uri"]
            params = "error=server_error"
            if oauth_request.get("state"):
                params += f"&state={oauth_request['state']}"
            redirect_url = f"{redirect_uri}?{params}"
    else:
        # User denied or unknown action - treat as denial
        redirect_uri = oauth_request["redirect_uri"]
        params = "error=access_denied"
        if oauth_request.get("state"):
            params += f"&state={oauth_request['state']}"

        redirect_url = f"{redirect_uri}?{params}"

        logger.info(
            f"User {oauth_request.get('user_id')} denied OAuth request for "
            f"client {oauth_request.get('client_id')}"
        )

    # Clear OAuth request from session and provider storage
    request.session.pop("oauth_request", None)
    oauth_state = request.session.pop("oauth_state", None)

    # Clean up OAuth request from provider storage
    if oauth_state:
        oauth_provider = getattr(request.app.state, "oauth_provider", None)
        if oauth_provider:
            oauth_provider.oauth_requests.pop(oauth_state, None)
            logger.info(f"Cleaned up OAuth request state: {oauth_state}")

    return RedirectResponse(url=redirect_url, status_code=302)


async def handle_logout(request: Request) -> RedirectResponse:
    """Process logout and clear session."""
    # Clear all session data
    request.session.clear()
    logger.info("User logged out successfully")
    return RedirectResponse(url="/auth/login", status_code=302)


def create_oauth_http_routes(get_async_session, oauth_provider=None) -> list[Route]:
    """Create all OAuth routes using MCP SDK."""
    # Use provided provider or create new instance
    provider = oauth_provider or MCPAnywhereAuthProvider(get_async_session)

    # Configure auth settings - use SERVER_URL as issuer (simple)
    auth_settings = AuthSettings(
        issuer_url=str(Config.SERVER_URL),
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mcp:read", "mcp:write"],
            default_scopes=["mcp:read"],
        ),
        resource_server_url=f"{Config.SERVER_URL}{Config.MCP_PATH_PREFIX}",
        service_documentation_url=f"{Config.SERVER_URL}/docs",
    )

    # Create MCP SDK auth routes - use as-is
    mcp_routes = create_auth_routes(
        provider=provider,
        issuer_url=auth_settings.issuer_url,
        service_documentation_url=auth_settings.service_documentation_url,
        client_registration_options=auth_settings.client_registration_options,
        revocation_options=auth_settings.revocation_options,
    )

    # Add protected resource metadata using vendor's helper
    # This provides the OAuth 2.0 Protected Resource Metadata endpoint (RFC 9728)
    # with proper CORS handling and spec compliance
    protected_resource_routes = create_protected_resource_routes(
        resource_url=f"{Config.SERVER_URL}{Config.MCP_PATH_PREFIX}",
        authorization_servers=[str(Config.SERVER_URL)],
        scopes_supported=["mcp:read", "mcp:write"],
    )

    # Add the protected resource routes to our routes list
    mcp_routes.extend(protected_resource_routes)

    # Add essential auth UI routes
    mcp_routes.append(Route("/auth/login", endpoint=login_page, methods=["GET"]))
    mcp_routes.append(Route("/auth/login", endpoint=handle_login, methods=["POST"]))
    mcp_routes.append(Route("/auth/consent", endpoint=consent_page, methods=["GET"]))
    mcp_routes.append(Route("/auth/consent", endpoint=handle_consent, methods=["POST"]))
    mcp_routes.append(Route("/auth/logout", endpoint=handle_logout, methods=["POST"]))

    return mcp_routes
