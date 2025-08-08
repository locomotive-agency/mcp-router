from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.applications import Starlette

from mcp_anywhere.transport.http_server import run_http_server


@pytest.mark.asyncio
async def test_run_http_server_creates_uvicorn_server():
    """Test that run_http_server creates and runs a uvicorn server."""
    with (
        patch("mcp_anywhere.transport.http_server.uvicorn") as mock_uvicorn,
        patch("mcp_anywhere.transport.http_server.create_app") as mock_create_app,
    ):
        # Setup mocks
        mock_app = Mock(spec=Starlette)
        mock_create_app.return_value = mock_app

        mock_config = Mock()
        mock_uvicorn.Config.return_value = mock_config

        mock_server = Mock()
        mock_server.serve = AsyncMock()
        mock_uvicorn.Server.return_value = mock_server

        # Run the function
        await run_http_server(host="0.0.0.0", port=8000)

        # Verify calls
        mock_create_app.assert_called_once()
        from unittest.mock import ANY

        mock_uvicorn.Config.assert_called_once_with(
            mock_app, host="0.0.0.0", port=8000, log_level=ANY
        )
        mock_uvicorn.Server.assert_called_once_with(mock_config)
        mock_server.serve.assert_called_once()


@pytest.mark.asyncio
async def test_run_http_server_with_custom_host_port():
    """Test that run_http_server accepts custom host and port."""
    with (
        patch("mcp_anywhere.transport.http_server.uvicorn") as mock_uvicorn,
        patch("mcp_anywhere.transport.http_server.create_app") as mock_create_app,
    ):
        # Setup mocks
        mock_app = Mock(spec=Starlette)
        mock_create_app.return_value = mock_app

        mock_config = Mock()
        mock_uvicorn.Config.return_value = mock_config

        mock_server = Mock()
        mock_server.serve = AsyncMock()
        mock_uvicorn.Server.return_value = mock_server

        # Run with custom values
        await run_http_server(host="127.0.0.1", port=9000)

        # Verify config was created with custom values
        from unittest.mock import ANY

        mock_uvicorn.Config.assert_called_once_with(
            mock_app, host="127.0.0.1", port=9000, log_level=ANY
        )


@pytest.mark.asyncio
async def test_run_http_server_handles_server_errors():
    """Test that run_http_server handles server startup errors gracefully."""
    with (
        patch("mcp_anywhere.transport.http_server.uvicorn") as mock_uvicorn,
        patch("mcp_anywhere.transport.http_server.create_app") as mock_create_app,
    ):
        # Setup mocks to raise an exception
        mock_app = Mock(spec=Starlette)
        mock_create_app.return_value = mock_app

        mock_config = Mock()
        mock_uvicorn.Config.return_value = mock_config

        mock_server = Mock()
        mock_server.serve = AsyncMock(side_effect=Exception("Server startup failed"))
        mock_uvicorn.Server.return_value = mock_server

        # Verify exception is propagated
        with pytest.raises(Exception, match="Server startup failed"):
            await run_http_server(host="0.0.0.0", port=8000)
