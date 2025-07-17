"""Tests for STDIO mode functionality."""

from unittest.mock import patch, MagicMock, Mock
from mcp_router.server import run_stdio_mode
from mcp_router.app import run_web_ui_in_background


class TestSTDIOMode:
    """Test the STDIO mode implementation."""

    @patch("mcp_router.server.log")
    @patch("mcp_router.server.create_router")
    @patch("mcp_router.server.get_active_servers")
    @patch("mcp_router.server.app.app_context")
    @patch("mcp_router.server.run_web_ui_in_background")
    def test_run_stdio_mode_sequence(
        self,
        mock_run_ui,
        mock_app_context,
        mock_get_servers,
        mock_create_router,
        mock_log,
    ):
        """Test that run_stdio_mode follows the correct sequence."""
        # Setup mocks
        mock_context = MagicMock()
        mock_app_context.return_value.__enter__ = Mock(return_value=mock_context)
        mock_app_context.return_value.__exit__ = Mock(return_value=None)
        mock_get_servers.return_value = []

        mock_router = MagicMock()
        mock_create_router.return_value = mock_router

        # Call the function
        run_stdio_mode()

        # Verify the sequence
        mock_run_ui.assert_called_once()
        mock_get_servers.assert_called_once()
        mock_create_router.assert_called_once_with([])
        mock_router.run.assert_called_once_with(transport="stdio")

        # Verify logging
        assert mock_log.info.call_count >= 2

    @patch("mcp_router.app.Thread")
    @patch("mcp_router.app.app")
    def test_run_web_ui_in_background_starts_thread(self, mock_app, mock_thread_class):
        """Test that run_web_ui_in_background starts a background thread."""
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        run_web_ui_in_background()

        # Verify thread was created with correct parameters
        mock_thread_class.assert_called_once()
        call_args = mock_thread_class.call_args
        assert call_args[1]["daemon"] is True
        assert "target" in call_args[1]

        # Verify thread was started
        mock_thread.start.assert_called_once()

    @patch("mcp_router.app.Config")
    @patch("mcp_router.app.app")
    @patch("mcp_router.app.Thread")
    def test_run_web_ui_background_app_config(self, mock_thread_class, mock_app, mock_config):
        """Test that the background web UI is configured correctly."""
        mock_config.FLASK_PORT = 8000
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        run_web_ui_in_background()

        # Get the target function from the Thread call
        call_args = mock_thread_class.call_args
        target_func = call_args[1]["target"]

        # Call the target function
        target_func()

        # Verify app.run was called with correct parameters
        mock_app.run.assert_called_once_with(
            host="0.0.0.0",
            port=8000,
            debug=False,
            use_reloader=False,
        )

    @patch("mcp_router.server.create_router")
    @patch("mcp_router.server.get_active_servers")
    @patch("mcp_router.server.app.app_context")
    @patch("mcp_router.server.run_web_ui_in_background")
    def test_stdio_mode_with_active_servers(
        self,
        mock_run_ui,
        mock_app_context,
        mock_get_servers,
        mock_create_router,
    ):
        """Test that stdio mode properly handles active servers."""
        # Setup mocks with some servers
        mock_context = MagicMock()
        mock_app_context.return_value.__enter__ = Mock(return_value=mock_context)
        mock_app_context.return_value.__exit__ = Mock(return_value=None)

        mock_servers = [MagicMock(name="test-server")]
        mock_get_servers.return_value = mock_servers

        mock_router = MagicMock()
        mock_create_router.return_value = mock_router

        # Call the function
        run_stdio_mode()

        # Verify servers were passed to router creation
        mock_create_router.assert_called_once_with(mock_servers)
        mock_router.run.assert_called_once_with(transport="stdio")
