"""OAuth routes using MCP SDK's auth module.
Provides all required endpoints including .well-known discovery.
"""

import time

from mcp.server.auth.routes import cors_middleware, create_auth_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from mcp_anywhere.auth.mcp_provider import MCPAnywhereAuthProvider
from mcp_anywhere.auth.models import User
from mcp_anywhere.config import Config
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)

# Templates for login/consent pages
templates = Jinja2Templates(directory="src/mcp_anywhere/web/templates")


async def login_page(request: Request) -> HTMLResponse:
    """Render the login page."""
    error = request.query_params.get("error")
    return templates.TemplateResponse(request, "auth/login.html", {"error": error})


async def handle_login(request: Request) -> RedirectResponse:
    """Process login form submission."""
    form = await request.form()
    username = form.get("username")
    password = form.get("password")

    # Get database session
    async with request.app.state.get_async_session() as session:
        stmt = select(User).where(User.username == username)
        user = await session.scalar(stmt)

        if user and user.check_password(password):
            # Set session
            request.session["user_id"] = user.id
            request.session["username"] = user.username

            # Redirect to original OAuth request or home
            next_url = request.query_params.get("next", "/")
            return RedirectResponse(url=next_url, status_code=302)

    # Login failed
    return RedirectResponse(url="/auth/login?error=invalid_credentials", status_code=302)


async def consent_page(request: Request) -> HTMLResponse:
    """Render the consent page."""
    oauth_request = request.session.get("oauth_request", {})

    if not oauth_request:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        request,
        "auth/consent.html",
        {
            "client_id": oauth_request.get("client_id"),
            "scope": oauth_request.get("scope"),
            "username": request.session.get("username"),
        },
    )


async def handle_consent(request: Request) -> RedirectResponse:
    """Process consent form submission."""
    form = await request.form()
    action = form.get("action")

    oauth_request = request.session.get("oauth_request", {})
    if not oauth_request:
        return RedirectResponse(url="/", status_code=302)

    provider = request.app.state.oauth_provider

    if action == "allow":
        # Generate authorization code
        code = await provider.create_authorization_code(request=request, **oauth_request)

        # Build redirect URL
        redirect_uri = oauth_request["redirect_uri"]
        params = f"code={code}"
        if oauth_request.get("state"):
            params += f"&state={oauth_request['state']}"

        redirect_url = f"{redirect_uri}?{params}"
    else:
        # User denied
        redirect_uri = oauth_request["redirect_uri"]
        params = "error=access_denied"
        if oauth_request.get("state"):
            params += f"&state={oauth_request['state']}"

        redirect_url = f"{redirect_uri}?{params}"

    # Clear OAuth request from session
    del request.session["oauth_request"]

    return RedirectResponse(url=redirect_url, status_code=302)


def create_oauth_routes(get_async_session) -> list[Route]:
    """Create all OAuth routes using MCP SDK.

    This includes:
    - /.well-known/oauth-authorization-server
    - /.well-known/oauth-protected-resource
    - /auth/authorize
    - /auth/token
    - /auth/introspect
    - /auth/revoke
    - /auth/register (optional)
    """
    # Create provider instance
    provider = MCPAnywhereAuthProvider(get_async_session)

    # Configure auth settings
    auth_settings = AuthSettings(
        issuer_url=str(Config.SERVER_URL),
        client_registration_options=ClientRegistrationOptions(
            enabled=False,  # Disable dynamic registration for security
            valid_scopes=["mcp:read", "mcp:write"],
            default_scopes=["mcp:read"],
        ),
        resource_server_url=f"{Config.SERVER_URL}/mcp",
        service_documentation_url=f"{Config.SERVER_URL}/docs",
    )

    # Create MCP SDK auth routes (includes .well-known endpoints)
    mcp_routes = create_auth_routes(
        provider=provider,
        issuer_url=auth_settings.issuer_url,
        service_documentation_url=auth_settings.service_documentation_url,
        client_registration_options=auth_settings.client_registration_options,
        revocation_options=auth_settings.revocation_options,
    )

    # Add our custom login/consent UI routes
    custom_routes = [
        Route("/auth/login", endpoint=login_page, methods=["GET"]),
        Route("/auth/login", endpoint=handle_login, methods=["POST"]),
        Route("/auth/consent", endpoint=consent_page, methods=["GET"]),
        Route("/auth/consent", endpoint=handle_consent, methods=["POST"]),
    ]

    # Add introspection endpoint for resource servers
    async def introspect_endpoint(request: Request) -> JSONResponse:
        """Token introspection endpoint (RFC 7662)."""
        form = await request.form()
        token = form.get("token")

        if not token:
            return JSONResponse({"active": False})

        access_token = await provider.introspect_token(token)

        if not access_token:
            return JSONResponse({"active": False})

        return JSONResponse(
            {
                "active": True,
                "client_id": access_token.client_id,
                "scope": " ".join(access_token.scopes),
                "exp": access_token.expires_at,
                "iat": int(time.time()),
                "token_type": "Bearer",
                "aud": access_token.resource,
            }
        )

    custom_routes.append(
        Route(
            "/auth/introspect",
            endpoint=cors_middleware(introspect_endpoint, ["POST", "OPTIONS"]),
            methods=["POST", "OPTIONS"],
        )
    )

    return mcp_routes + custom_routes
