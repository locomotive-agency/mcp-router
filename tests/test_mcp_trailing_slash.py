from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware import Middleware as StarletteMiddleware
from starlette.testclient import TestClient

from mcp_anywhere.auth.routes import create_oauth_http_routes
from mcp_anywhere.web.app import RedirectMiddleware


@asynccontextmanager
async def _dummy_session_factory():
    # Minimal async context manager to satisfy provider construction
    yield None


def _build_auth_app():
    routes = create_oauth_http_routes(get_async_session=_dummy_session_factory)
    return Starlette(routes=routes)


def _build_redirect_app():
    middleware = [StarletteMiddleware(RedirectMiddleware)]
    return Starlette(middleware=middleware)


def test_protected_resource_metadata_trailing_slash():
    app = _build_auth_app()
    client = TestClient(app)

    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resource"].endswith("/mcp/")


def test_mcp_redirects_to_trailing_slash():
    app = _build_redirect_app()
    client = TestClient(app, follow_redirects=False)

    resp = client.get("/mcp")
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location", "").endswith("/mcp/")
