"""Test Claude analyzer runtime type detection and environment variable parsing."""

import pytest
from unittest.mock import patch, AsyncMock

from src.mcp_anywhere.claude_analyzer import AsyncClaudeAnalyzer


@pytest.mark.asyncio
async def test_node_js_runtime_detection():
    """Test that Node.js servers are properly detected with npx runtime."""
    analyzer = AsyncClaudeAnalyzer()
    
    # Mock Claude response for Node.js server
    mock_response = """
RUNTIME: npx
INSTALL: npm install -g @ahrefs/mcp
START: npx @ahrefs/mcp
NAME: ahrefs-mcp
DESCRIPTION: Ahrefs MCP server for SEO data access
ENV_VARS:
- KEY: AHREFS_API_TOKEN, DESC: API token for Ahrefs access, REQUIRED: true
- KEY: RATE_LIMIT, DESC: Rate limit for API calls, REQUIRED: false
"""
    
    result = analyzer._parse_claude_response(mock_response)
    
    assert result["runtime_type"] == "npx"
    assert result["install_command"] == "npm install -g @ahrefs/mcp"
    assert result["start_command"] == "npx @ahrefs/mcp"
    assert result["name"] == "ahrefs-mcp"
    assert result["description"] == "Ahrefs MCP server for SEO data access"
    
    # Check environment variables
    assert len(result["env_variables"]) == 2
    assert result["env_variables"][0]["key"] == "AHREFS_API_TOKEN"
    assert result["env_variables"][0]["required"] is True
    assert result["env_variables"][1]["key"] == "RATE_LIMIT"
    assert result["env_variables"][1]["required"] is False


@pytest.mark.asyncio
async def test_python_runtime_detection():
    """Test that Python servers are properly detected with uvx runtime."""
    analyzer = AsyncClaudeAnalyzer()
    
    # Mock Claude response for Python server
    mock_response = """
RUNTIME: uvx
INSTALL: pip install mcp-python-interpreter
START: uvx mcp-python-interpreter
NAME: python-interpreter
DESCRIPTION: Python interpreter MCP server
ENV_VARS:
- KEY: PYTHON_PATH, DESC: Python executable path, REQUIRED: false
"""
    
    result = analyzer._parse_claude_response(mock_response)
    
    assert result["runtime_type"] == "uvx"
    assert result["install_command"] == "pip install mcp-python-interpreter"
    assert result["start_command"] == "uvx mcp-python-interpreter"
    assert result["name"] == "python-interpreter"
    assert len(result["env_variables"]) == 1
    assert result["env_variables"][0]["key"] == "PYTHON_PATH"


def test_runtime_type_mapping():
    """Test that runtime types are properly mapped for template compatibility."""
    analyzer = AsyncClaudeAnalyzer()
    
    # Test npx -> npx (keep as is for container manager)
    response_npx = "RUNTIME: npx\nINSTALL: npm install -g @test/mcp\nSTART: npx @test/mcp\nNAME: test\nDESCRIPTION: test"
    result = analyzer._parse_claude_response(response_npx)
    assert result["runtime_type"] == "npx"
    
    # Test uvx -> uvx (keep as is for container manager)
    response_uvx = "RUNTIME: uvx\nINSTALL: pip install test\nSTART: uvx test\nNAME: test\nDESCRIPTION: test"
    result = analyzer._parse_claude_response(response_uvx)
    assert result["runtime_type"] == "uvx"


def test_env_variables_parsing_edge_cases():
    """Test environment variable parsing with various formats."""
    analyzer = AsyncClaudeAnalyzer()
    
    # Test with missing parts
    response = """
RUNTIME: npx
INSTALL: npm install -g test
START: npx test
NAME: test
DESCRIPTION: test
ENV_VARS:
- KEY: API_KEY, DESC: Required API key, REQUIRED: true
- KEY: OPTIONAL_VAR, DESC: Optional variable
- KEY: MALFORMED_LINE
"""
    
    result = analyzer._parse_claude_response(response)
    
    # Should parse all three - the "malformed" one is actually valid (just key with no desc)
    assert len(result["env_variables"]) == 3
    assert result["env_variables"][0]["key"] == "API_KEY"
    assert result["env_variables"][0]["required"] is True
    assert result["env_variables"][1]["key"] == "OPTIONAL_VAR"
    assert result["env_variables"][1]["required"] is True  # Default to true if not specified