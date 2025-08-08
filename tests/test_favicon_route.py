"""Test favicon route handling."""

import httpx
import pytest

from mcp_anywhere.web.app import create_app


@pytest.mark.asyncio
async def test_favicon_returns_204():
    """Test that favicon.ico route returns 204 No Content."""
    app = await create_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/favicon.ico")

        assert response.status_code == 204
        assert response.content == b""


@pytest.mark.asyncio
async def test_favicon_method_not_allowed():
    """Test that favicon.ico only accepts GET requests."""
    app = await create_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/favicon.ico")

        assert response.status_code == 405  # Method Not Allowed
