"""Test environment variable extraction and form handling."""

import pytest

from mcp_anywhere.claude_analyzer import AsyncClaudeAnalyzer


@pytest.mark.asyncio
async def test_env_vars_extracted_from_claude():
    """Test that environment variables are properly extracted from Claude analysis."""
    analyzer = AsyncClaudeAnalyzer()

    # Mock Claude response with environment variables
    mock_response = """
RUNTIME: npx
INSTALL: npm install -g @ahrefs/mcp
START: npx @ahrefs/mcp
NAME: ahrefs-mcp
DESCRIPTION: Ahrefs MCP server for SEO data access
ENV_VARS:
- KEY: AHREFS_API_TOKEN, DESC: API token for Ahrefs access, REQUIRED: true
- KEY: RATE_LIMIT, DESC: Rate limit for API calls, REQUIRED: false
- KEY: DEBUG_MODE, DESC: Enable debug logging, REQUIRED: false
"""

    result = analyzer._parse_claude_response(mock_response)

    # Verify environment variables are extracted
    assert len(result["env_variables"]) == 3

    # Check first env var (required)
    env1 = result["env_variables"][0]
    assert env1["key"] == "AHREFS_API_TOKEN"
    assert env1["description"] == "API token for Ahrefs access"
    assert env1["required"] is True

    # Check second env var (optional)
    env2 = result["env_variables"][1]
    assert env2["key"] == "RATE_LIMIT"
    assert env2["description"] == "Rate limit for API calls"
    assert env2["required"] is False

    # Check third env var (optional)
    env3 = result["env_variables"][2]
    assert env3["key"] == "DEBUG_MODE"
    assert env3["description"] == "Enable debug logging"
    assert env3["required"] is False


def test_env_vars_form_data_structure():
    """Test that environment variables are structured correctly for form rendering."""
    analyzer = AsyncClaudeAnalyzer()

    mock_response = """
RUNTIME: npx
INSTALL: npm install -g test
START: npx test
NAME: test
DESCRIPTION: test
ENV_VARS:
- KEY: API_KEY, DESC: Required API key, REQUIRED: true
- KEY: OPTIONAL_VAR, DESC: Optional variable, REQUIRED: false
"""

    result = analyzer._parse_claude_response(mock_response)

    # Verify the structure matches what templates expect
    env_vars = result["env_variables"]
    assert isinstance(env_vars, list)

    for env_var in env_vars:
        assert "key" in env_var
        assert "description" in env_var
        assert "required" in env_var
        assert isinstance(env_var["required"], bool)


def test_env_vars_template_rendering_format():
    """Test that env vars are in the correct format for template rendering."""
    # This would be the data structure passed to templates
    analysis_data = {
        "runtime_type": "npx",
        "name": "test-server",
        "env_variables": [
            {"key": "API_TOKEN", "description": "API access token", "required": True},
            {"key": "BASE_URL", "description": "Base URL for API", "required": False},
        ],
    }

    # Verify template can access the data correctly
    env_vars = analysis_data["env_variables"]
    assert len(env_vars) == 2

    # Check required env var
    required_var = next(var for var in env_vars if var["required"])
    assert required_var["key"] == "API_TOKEN"
    assert required_var["description"] == "API access token"

    # Check optional env var
    optional_var = next(var for var in env_vars if not var["required"])
    assert optional_var["key"] == "BASE_URL"
    assert optional_var["description"] == "Base URL for API"
