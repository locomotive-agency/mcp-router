from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import pytest_asyncio

from mcp_anywhere.claude_analyzer import AsyncClaudeAnalyzer


@pytest_asyncio.fixture
async def analyzer():
    """Test fixture for AsyncClaudeAnalyzer with mocked credentials."""
    with patch("mcp_anywhere.claude_analyzer.Config") as mock_config:
        mock_config.ANTHROPIC_API_KEY = "test-api-key"
        mock_config.GITHUB_TOKEN = "test-github-token"
        mock_config.ANTHROPIC_MODEL_NAME = "claude-3-sonnet-20240229"
        return AsyncClaudeAnalyzer()


@pytest.mark.asyncio
async def test_async_claude_analyzer_initialization(analyzer):
    """Test that AsyncClaudeAnalyzer initializes correctly."""
    assert analyzer.api_key == "test-api-key"
    assert analyzer.github_token == "test-github-token"
    assert analyzer.model_name == "claude-3-sonnet-20240229"


@pytest.mark.asyncio
async def test_analyze_repository_success(analyzer):
    """Test successful repository analysis with async httpx and Claude API."""

    # Mock GitHub API responses
    mock_readme = {
        "content": "IyBNQ1AgU2VydmVyCgpBIHRlc3QgTUNQIHNlcnZlciBmb3IgZmluYW5jaWFsIGRhdGEu"  # "# MCP Server\n\nA test MCP server for financial data." base64 encoded
    }
    mock_package_json = {
        "content": "eyJuYW1lIjogIkBleGFtcGxlL21jcC1zZXJ2ZXIiLCAidmVyc2lvbiI6ICIxLjAuMCJ9"  # {"name": "@example/mcp-server", "version": "1.0.0"} base64 encoded
    }

    # Mock Claude API response
    mock_claude_response = """RUNTIME: npx
INSTALL: npm install -g @example/mcp-server
START: npx @example/mcp-server
NAME: financial-data-mcp
DESCRIPTION: A test MCP server for financial data analysis
ENV_VARS:
- KEY: API_KEY, DESC: API key for financial data service, REQUIRED: true
- KEY: DEBUG, DESC: Enable debug logging, REQUIRED: false"""

    with patch("httpx.AsyncClient") as mock_client_class:
        # Mock httpx client
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        # Mock GitHub API calls
        mock_readme_response = Mock()
        mock_readme_response.json.return_value = mock_readme
        mock_readme_response.raise_for_status = Mock()

        mock_package_response = Mock()
        mock_package_response.json.return_value = mock_package_json
        mock_package_response.raise_for_status = Mock()

        mock_pyproject_response = Mock()
        mock_pyproject_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=Mock(status_code=404)
        )

        mock_client.get.side_effect = [
            mock_readme_response,
            mock_package_response,
            mock_pyproject_response,
        ]

        # Mock Anthropic client
        with patch.object(analyzer, "client") as mock_anthropic:
            mock_message = Mock()
            mock_message.content = [Mock(text=mock_claude_response)]
            mock_anthropic.messages.create.return_value = mock_message

            # Test the analysis
            result = await analyzer.analyze_repository("https://github.com/example/mcp-server")

    # Verify the result
    assert result["runtime_type"] == "npx"
    assert result["install_command"] == "npm install -g @example/mcp-server"
    assert result["start_command"] == "npx @example/mcp-server"
    assert result["name"] == "financial-data-mcp"
    assert result["description"] == "A test MCP server for financial data analysis"
    assert len(result["env_variables"]) == 2
    assert result["env_variables"][0]["key"] == "API_KEY"
    assert result["env_variables"][0]["required"] is True
    assert result["env_variables"][1]["key"] == "DEBUG"
    assert result["env_variables"][1]["required"] is False


@pytest.mark.asyncio
async def test_analyze_repository_invalid_url(analyzer):
    """Test that invalid GitHub URLs raise ValueError."""
    with pytest.raises(ValueError, match="Invalid GitHub URL format"):
        await analyzer.analyze_repository("https://notgithub.com/owner/repo")


@pytest.mark.asyncio
async def test_analyze_repository_github_api_error(analyzer):
    """Test handling of GitHub API errors."""

    # Mock the _fetch_file method directly to simulate GitHub API error
    mock_response = Mock()
    mock_response.status_code = 500
    mock_request = Mock()
    error = httpx.HTTPStatusError("Server Error", request=mock_request, response=mock_response)

    with patch.object(analyzer, "_fetch_file", side_effect=error):
        with pytest.raises(ConnectionError, match="Failed to fetch files from GitHub"):
            await analyzer.analyze_repository("https://github.com/example/repo")


@pytest.mark.asyncio
async def test_analyze_repository_claude_api_error(analyzer):
    """Test handling of Claude API errors."""

    # Mock successful GitHub API calls
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        mock_response = Mock()
        mock_response.json.return_value = {"content": "dGVzdA=="}  # "test" base64 encoded
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        # Mock Claude API method directly to avoid retry complications
        with patch.object(analyzer, "_call_claude_api") as mock_call_claude:
            from anthropic import AnthropicError

            mock_call_claude.side_effect = AnthropicError("API Error")

            with pytest.raises(ConnectionError, match="Failed to get analysis from Claude"):
                await analyzer.analyze_repository("https://github.com/example/repo")


@pytest.mark.asyncio
async def test_fetch_file_success(analyzer):
    """Test successful file fetching from GitHub."""

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        mock_response = Mock()
        mock_response.json.return_value = {
            "content": "dGVzdCBjb250ZW50"
        }  # "test content" base64 encoded
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        result = await analyzer._fetch_file("owner", "repo", "README.md")

        assert result == "test content"
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_file_not_found(analyzer):
    """Test handling of file not found (404) errors."""

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        mock_response = Mock()
        mock_response.status_code = 404
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=mock_response
        )

        result = await analyzer._fetch_file("owner", "repo", "nonexistent.md")

        assert result is None


@pytest.mark.asyncio
async def test_parse_claude_response():
    """Test parsing of Claude's structured response."""
    response_text = """RUNTIME: uvx
INSTALL: pip install financial-mcp
START: uvx financial-mcp
NAME: financial-data-server
DESCRIPTION: Provides financial market data through MCP
ENV_VARS:
- KEY: API_TOKEN, DESC: Token for market data API, REQUIRED: true
- KEY: CACHE_SIZE, DESC: Number of requests to cache, REQUIRED: false"""

    analyzer = AsyncClaudeAnalyzer.__new__(AsyncClaudeAnalyzer)  # Create without __init__
    result = analyzer._parse_claude_response(response_text)

    assert result["runtime_type"] == "uvx"
    assert result["install_command"] == "pip install financial-mcp"
    assert result["start_command"] == "uvx financial-mcp"
    assert result["name"] == "financial-data-server"
    assert result["description"] == "Provides financial market data through MCP"
    assert len(result["env_variables"]) == 2
    assert result["env_variables"][0]["key"] == "API_TOKEN"
    assert result["env_variables"][0]["required"] is True


@pytest.mark.asyncio
async def test_call_claude_api_success(analyzer):
    """Test successful Claude API call."""

    mock_claude_response = """RUNTIME: npx
INSTALL: npm install -g test-package
START: npx test-package
NAME: test-server
DESCRIPTION: A test server
ENV_VARS:"""

    with patch.object(analyzer, "client") as mock_anthropic:
        mock_message = Mock()
        mock_message.content = [Mock(text=mock_claude_response)]
        mock_anthropic.messages.create.return_value = mock_message

        result = await analyzer._call_claude_api("test prompt")

        assert result == mock_claude_response
        mock_anthropic.messages.create.assert_called_once()
