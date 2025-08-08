from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from starlette.applications import Starlette

from mcp_anywhere.transport.stdio_server import run_stdio_server


@pytest.mark.asyncio
async def test_run_stdio_server_creates_uvicorn_server():
    """It should create the app and run a uvicorn server for the admin UI."""
    with (
        patch("mcp_anywhere.transport.stdio_server.uvicorn") as mock_uvicorn,
        patch("mcp_anywhere.transport.stdio_server.create_app") as mock_create_app,
    ):
        mock_app = Mock(spec=Starlette)
        mock_create_app.return_value = mock_app

        mock_config = Mock()
        mock_uvicorn.Config.return_value = mock_config

        mock_server = Mock()
        mock_server.serve = AsyncMock()
        mock_uvicorn.Server.return_value = mock_server

        await run_stdio_server(host="127.0.0.1", port=9001)

        mock_create_app.assert_called_once_with(transport_mode="stdio")
        mock_uvicorn.Config.assert_called_once_with(
            mock_app, host="127.0.0.1", port=9001, log_level=ANY
        )
        # uvicorn.Server may be called with positional or keyword args depending on version
        # Accept either form to keep the test resilient
        try:
            mock_uvicorn.Server.assert_called_once_with(mock_config)
        except AssertionError:
            mock_uvicorn.Server.assert_called_once_with(config=mock_config)
        mock_server.serve.assert_called_once()


@pytest.mark.asyncio
async def test_run_stdio_server_handles_server_errors():
    """It should surface server startup errors cleanly."""
    with (
        patch("mcp_anywhere.transport.stdio_server.uvicorn") as mock_uvicorn,
        patch("mcp_anywhere.transport.stdio_server.create_app") as mock_create_app,
    ):
        mock_app = Mock(spec=Starlette)
        mock_create_app.return_value = mock_app

        mock_config = Mock()
        mock_uvicorn.Config.return_value = mock_config

        mock_server = Mock()
        mock_server.serve = AsyncMock(side_effect=Exception("Server startup failed"))
        mock_uvicorn.Server.return_value = mock_server

        with pytest.raises(Exception, match="Server startup failed"):
            await run_stdio_server(host="0.0.0.0", port=8000)
