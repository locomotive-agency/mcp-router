"""Authentication and OAuth routes for MCP Anywhere."""

from typing import List, Callable
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates
from sqlalchemy import select

from mcp_anywhere.auth.models import User
from mcp_anywhere.auth.oauth_server import SimpleAuthorizationServer
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)

# Template engine
templates = Jinja2Templates(directory="src/mcp_anywhere/web/templates")


async def login_get(request: Request) -> HTMLResponse:
    """Render login form."""
    return templates.TemplateResponse(request, "auth/login.html", {
        "request": request,
        "error": request.query_params.get("error")
    })


async def login_post(request: Request) -> HTMLResponse | RedirectResponse:
    """Handle login form submission."""
    try:
        form_data = await request.form()
        username = form_data.get("username", "").strip()
        password = form_data.get("password", "")
        
        if not username or not password:
            return templates.TemplateResponse(request, "auth/login.html", {
                "request": request,
                "error": "Username and password are required",
                "username": username
            })
        
        # Get database session
        get_session = request.app.state.get_async_session
        async with get_session() as db_session:
            # Find user by username
            stmt = select(User).where(User.username == username)
            result = await db_session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user or not user.check_password(password):
                logger.warning(f"Failed login attempt for username: {username}")
                return templates.TemplateResponse(request, "auth/login.html", {
                    "request": request,
                    "error": "Invalid username or password",
                    "username": username
                })
            
            # Successful login - set session
            request.session["user_id"] = user.id
            request.session["username"] = user.username
            
            logger.info(f"User logged in: {username}")
            
            # Redirect to intended page or home
            redirect_url = request.query_params.get("next", "/")
            return RedirectResponse(url=redirect_url, status_code=302)
            
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return templates.TemplateResponse(request, "auth/login.html", {
            "request": request,
            "error": "An error occurred during login"
        })


async def logout_post(request: Request) -> RedirectResponse:
    """Handle logout."""
    try:
        username = request.session.get("username", "unknown")
        request.session.clear()
        logger.info(f"User logged out: {username}")
        
        return RedirectResponse(url="/", status_code=302)
        
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        return RedirectResponse(url="/", status_code=302)


async def authorize_get(request: Request) -> HTMLResponse | RedirectResponse:
    """Handle OAuth authorization request (GET)."""
    try:
        # Check if user is logged in
        user_id = request.session.get("user_id")
        if not user_id:
            # Redirect to login with current URL as next parameter
            login_url = f"/auth/login?next={request.url}"
            return RedirectResponse(url=login_url, status_code=302)
        
        # Get database session and OAuth server
        get_session = request.app.state.get_async_session
        async with get_session() as db_session:
            oauth_server = SimpleAuthorizationServer(db_session)
            
            # Validate OAuth parameters
            if not await oauth_server.validate_authorize_request(request):
                return JSONResponse(
                    {"error": "invalid_request", "error_description": "Invalid OAuth parameters"},
                    status_code=400
                )
            
            # Get OAuth parameters from session
            oauth_params = request.session.get("oauth_params", {})
            client_id = oauth_params.get("client_id")
            scope = oauth_params.get("scope", "")
            
            # Render consent page
            return templates.TemplateResponse(request, "auth/consent.html", {
                "request": request,
                "client_id": client_id,
                "scope": scope,
                "username": request.session.get("username")
            })
            
    except Exception as e:
        logger.error(f"Error in authorize GET: {e}")
        return JSONResponse(
            {"error": "server_error", "error_description": "Internal server error"},
            status_code=500
        )


async def authorize_post(request: Request) -> RedirectResponse:
    """Handle OAuth authorization decision (POST)."""
    try:
        form_data = await request.form()
        action = form_data.get("action")
        
        # Determine if user granted access
        grant = action == "allow"
        
        # Get database session and OAuth server
        get_session = request.app.state.get_async_session
        async with get_session() as db_session:
            oauth_server = SimpleAuthorizationServer(db_session)
            
            # Create authorization response
            return await oauth_server.create_authorization_response(request, grant)
            
    except Exception as e:
        logger.error(f"Error in authorize POST: {e}")
        # Try to get redirect URI from session for error redirect
        oauth_params = request.session.get("oauth_params", {})
        redirect_uri = oauth_params.get("redirect_uri")
        
        if redirect_uri:
            error_url = f"{redirect_uri}?error=server_error"
            return RedirectResponse(url=error_url, status_code=302)
        else:
            return JSONResponse(
                {"error": "server_error", "error_description": "Internal server error"},
                status_code=500
            )


async def token_post(request: Request) -> JSONResponse:
    """Handle OAuth token request (POST)."""
    try:
        # Get database session and OAuth server
        get_session = request.app.state.get_async_session
        async with get_session() as db_session:
            oauth_server = SimpleAuthorizationServer(db_session)
            
            # Create token response
            return await oauth_server.create_token_response(request)
            
    except Exception as e:
        logger.error(f"Error in token endpoint: {e}")
        return JSONResponse(
            {"error": "server_error", "error_description": "Internal server error"},
            status_code=500
        )


def auth_routes(get_async_session_func: Callable = None) -> List[Route]:
    """
    Create authentication routes.
    
    Args:
        get_async_session_func: Function to get async database session
        
    Returns:
        List of Starlette Route objects
    """
    return [
        Route("/auth/login", login_get, methods=["GET"]),
        Route("/auth/login", login_post, methods=["POST"]),
        Route("/auth/logout", logout_post, methods=["POST"]),
        Route("/auth/authorize", authorize_get, methods=["GET"]),
        Route("/auth/authorize", authorize_post, methods=["POST"]),
        Route("/auth/token", token_post, methods=["POST"]),
    ]