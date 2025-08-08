import pytest
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from mcp_anywhere.web.app import create_app


def _has_static_mount(app) -> bool:
    for route in app.routes:
        if (
            isinstance(route, Mount)
            and route.path == "/static"
            and isinstance(route.app, StaticFiles)
        ):
            return True
    return False


@pytest.mark.asyncio
async def test_static_mount_present_in_http_mode():
    app = await create_app(transport_mode="http")
    assert _has_static_mount(app)


@pytest.mark.asyncio
async def test_static_mount_present_in_stdio_mode():
    app = await create_app(transport_mode="stdio")
    assert _has_static_mount(app)
