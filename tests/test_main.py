"""Tests for the main entry point functionality."""

import os
from unittest.mock import patch


class TestMain:
    """Test the main entry point function."""

    @patch("mcp_router.__main__.run_stdio_mode")
    @patch("mcp_router.__main__.run_http_mode")
    def test_main_calls_stdio_mode_with_arg(self, mock_run_http, mock_run_stdio):
        """Test that main() calls run_stdio_mode when --transport stdio is passed."""
        from mcp_router.__main__ import main

        with patch("sys.argv", ["mcp_router", "--transport", "stdio"]):
            main()
        mock_run_stdio.assert_called_once()
        mock_run_http.assert_not_called()

    @patch("mcp_router.__main__.run_stdio_mode")
    @patch("mcp_router.__main__.run_http_mode")
    def test_main_calls_http_mode_with_arg(self, mock_run_http, mock_run_stdio):
        """Test that main() calls run_http_mode when --transport http is passed."""
        from mcp_router.__main__ import main

        with patch("sys.argv", ["mcp_router", "--transport", "http"]):
            main()
        mock_run_http.assert_called_once()
        mock_run_stdio.assert_not_called()

    @patch("mcp_router.__main__.run_stdio_mode")
    @patch("mcp_router.__main__.run_http_mode")
    def test_main_defaults_to_http_mode(self, mock_run_http, mock_run_stdio):
        """Test that main() defaults to HTTP mode when no args are passed."""
        from mcp_router.__main__ import main

        # Ensure MCP_TRANSPORT env var is not set for this test
        with patch.dict(os.environ, {}, clear=False) as mock_env:
            # Remove MCP_TRANSPORT if it exists
            mock_env.pop("MCP_TRANSPORT", None)
            with patch("sys.argv", ["mcp_router"]):
                main()
        mock_run_http.assert_called_once()
        mock_run_stdio.assert_not_called()

    @patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"})
    @patch("mcp_router.__main__.run_stdio_mode")
    @patch("mcp_router.__main__.run_http_mode")
    def test_main_uses_env_var_stdio(self, mock_run_http, mock_run_stdio):
        """Test that main() uses MCP_TRANSPORT env var when set to stdio."""
        from mcp_router.__main__ import main

        with patch("sys.argv", ["mcp_router"]):
            main()
        mock_run_stdio.assert_called_once()
        mock_run_http.assert_not_called()

    @patch.dict(os.environ, {"MCP_TRANSPORT": "http"})
    @patch("mcp_router.__main__.run_stdio_mode")
    @patch("mcp_router.__main__.run_http_mode")
    def test_main_uses_env_var_http(self, mock_run_http, mock_run_stdio):
        """Test that main() uses MCP_TRANSPORT env var when set to http."""
        from mcp_router.__main__ import main

        with patch("sys.argv", ["mcp_router"]):
            main()
        mock_run_http.assert_called_once()
        mock_run_stdio.assert_not_called()

    @patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"})
    @patch("mcp_router.__main__.run_stdio_mode")
    @patch("mcp_router.__main__.run_http_mode")
    def test_command_line_overrides_env_var(self, mock_run_http, mock_run_stdio):
        """Test that command line args override environment variables."""
        from mcp_router.__main__ import main

        with patch("sys.argv", ["mcp_router", "--transport", "http"]):
            main()
        mock_run_http.assert_called_once()
        mock_run_stdio.assert_not_called()

    @patch.dict(os.environ, {"MCP_TRANSPORT": "STDIO"})
    @patch("mcp_router.__main__.run_stdio_mode")
    @patch("mcp_router.__main__.run_http_mode")
    def test_env_var_case_insensitive(self, mock_run_http, mock_run_stdio):
        """Test that MCP_TRANSPORT env var is case-insensitive."""
        from mcp_router.__main__ import main

        with patch("sys.argv", ["mcp_router"]):
            main()
        mock_run_stdio.assert_called_once()
        mock_run_http.assert_not_called()
