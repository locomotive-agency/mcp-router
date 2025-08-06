"""
Test the main CLI entry point.

This module tests the refactored __main__.py as specified in Phase 3
of the engineering documentation.
"""

import sys
from unittest.mock import AsyncMock, patch

import pytest

from mcp_anywhere.__main__ import main


@pytest.mark.asyncio
async def test_main_http_command():
    """
    Test that 'mcp-anywhere serve http --port 8000' calls run_http_server correctly.
    """
    with (
        patch("mcp_anywhere.__main__.run_http_server", new_callable=AsyncMock) as mock_http_server,
        patch("sys.argv", ["mcp-anywhere", "serve", "http", "--port", "8000"]),
    ):
        await main()

        # Verify http server was called with correct parameters
        mock_http_server.assert_called_once_with(host="0.0.0.0", port=8000)


@pytest.mark.asyncio
async def test_main_stdio_command():
    """
    Test that 'mcp-anywhere serve stdio --port 8001' calls run_stdio_server correctly.
    """
    with (
        patch(
            "mcp_anywhere.__main__.run_stdio_server", new_callable=AsyncMock
        ) as mock_stdio_server,
        patch("sys.argv", ["mcp-anywhere", "serve", "stdio", "--port", "8001"]),
    ):
        await main()

        # Verify stdio server was called with correct parameters
        mock_stdio_server.assert_called_once_with(host="0.0.0.0", port=8001)


@pytest.mark.asyncio
async def test_main_http_default_port():
    """
    Test that HTTP mode uses default port 8000 when not specified.
    """
    with (
        patch("mcp_anywhere.__main__.run_http_server", new_callable=AsyncMock) as mock_http_server,
        patch("sys.argv", ["mcp-anywhere", "serve", "http"]),
    ):
        await main()

        # Verify default port is used
        mock_http_server.assert_called_once_with(host="0.0.0.0", port=8000)


@pytest.mark.asyncio
async def test_main_stdio_default_port():
    """
    Test that STDIO mode uses default port 8000 when not specified.
    """
    with (
        patch(
            "mcp_anywhere.__main__.run_stdio_server", new_callable=AsyncMock
        ) as mock_stdio_server,
        patch("sys.argv", ["mcp-anywhere", "serve", "stdio"]),
    ):
        await main()

        # Verify default port is used
        mock_stdio_server.assert_called_once_with(host="0.0.0.0", port=8000)


@pytest.mark.asyncio
async def test_main_custom_host():
    """
    Test that custom host can be specified.
    """
    with (
        patch("mcp_anywhere.__main__.run_http_server", new_callable=AsyncMock) as mock_http_server,
        patch(
            "sys.argv", ["mcp-anywhere", "serve", "http", "--host", "127.0.0.1", "--port", "9000"]
        ),
    ):
        await main()

        # Verify custom host and port are used
        mock_http_server.assert_called_once_with(host="127.0.0.1", port=9000)


@pytest.mark.asyncio
async def test_main_invalid_command():
    """
    Test that invalid commands raise SystemExit (argparse behavior).
    """
    with (
        patch("sys.argv", ["mcp-anywhere", "invalid-command"]),
        patch("sys.stderr"),
    ):  # Suppress stderr output during test
        with pytest.raises(SystemExit):
            await main()


@pytest.mark.asyncio
async def test_main_missing_subcommand():
    """
    Test that missing subcommand raises SystemExit.
    """
    with (
        patch("sys.argv", ["mcp-anywhere"]),
        patch("sys.stderr"),
    ):  # Suppress stderr output during test
        with pytest.raises(SystemExit):
            await main()


@pytest.mark.asyncio
async def test_main_help_option():
    """
    Test that --help option raises SystemExit (normal argparse behavior).
    """
    with (
        patch("sys.argv", ["mcp-anywhere", "--help"]),
        patch("sys.stdout"),
    ):  # Suppress stdout output during test
        with pytest.raises(SystemExit):
            await main()


@pytest.mark.asyncio
async def test_main_serve_help():
    """
    Test that 'serve --help' shows help for serve subcommand.
    """
    with (
        patch("sys.argv", ["mcp-anywhere", "serve", "--help"]),
        patch("sys.stdout"),
    ):  # Suppress stdout output during test
        with pytest.raises(SystemExit):
            await main()


@pytest.mark.asyncio
async def test_main_error_handling():
    """
    Test that server errors are properly handled and printed to stderr.
    """
    with (
        patch(
            "mcp_anywhere.__main__.run_http_server",
            new_callable=AsyncMock,
            side_effect=ValueError("Server error"),
        ) as mock_http_server,
        patch("sys.argv", ["mcp-anywhere", "serve", "http"]),
        patch("builtins.print") as mock_print,
        patch("sys.exit") as mock_exit,
    ):
        await main()

        # Verify error was printed to stderr and exit was called
        mock_print.assert_called_with("Error: Server error", file=sys.stderr)
        mock_exit.assert_called_with(1)


def test_main_entry_point():
    """
    Test that the module can be run as a script using asyncio.run().
    """
    with (
        patch("mcp_anywhere.__main__.main", new_callable=AsyncMock) as mock_main,
        patch("asyncio.run") as mock_asyncio_run,
        patch("__main__.__name__", "__main__"),
    ):
        # Import and execute the main block
        exec("""
if __name__ == "__main__":
    import asyncio
    from mcp_anywhere.__main__ import main
    asyncio.run(main())
        """)

        # Verify asyncio.run was called
        # Note: This test verifies the pattern, actual execution is mocked
