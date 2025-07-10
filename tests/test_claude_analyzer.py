"""Tests for the ClaudeAnalyzer"""

import pytest
import respx
from httpx import Response
from mcp_router.claude_analyzer import ClaudeAnalyzer

# --- Test Data ---

FAKE_GITHUB_URL = "https://github.com/test-owner/test-repo"
FAKE_README_CONTENT = "This is the README for the test repo."
FAKE_PACKAGE_JSON_CONTENT = '{"name": "test-repo-pkg", "scripts": {"start": "npx start-server"}}'
FAKE_CLAUDE_RESPONSE = """
RUNTIME: npx
INSTALL: npm install
START: npx start-server
NAME: test-repo-pkg
DESCRIPTION: A test repository for analysis.
ENV_VARS:
- KEY: API_KEY, DESC: An API key, REQUIRED: true
- KEY: OPTIONAL_FLAG, DESC: An optional flag, REQUIRED: false
"""

# --- Helper to Mock GitHub API ---


def mock_github_api(respx_mock, readme_status=200, pkg_json_status=200, pyproject_status=404):
    """Mocks the GitHub API endpoints for fetching files."""
    base_url = "https://api.github.com/repos/test-owner/test-repo/contents"

    readme_response = {"content": b"This is the README for the test repo.".hex()}
    respx_mock.get(f"{base_url}/README.md").mock(
        return_value=Response(readme_status, json=readme_response if readme_status == 200 else {})
    )

    pkg_json_response = {"content": FAKE_PACKAGE_JSON_CONTENT.encode("utf-8").hex()}
    respx_mock.get(f"{base_url}/package.json").mock(
        return_value=Response(
            pkg_json_status, json=pkg_json_response if pkg_json_status == 200 else {}
        )
    )

    respx_mock.get(f"{base_url}/pyproject.toml").mock(return_value=Response(pyproject_status))


# --- Tests ---


@respx.mock
def test_analyze_repository_success(respx_mock, mocker):
    """Test successful analysis of a repository."""
    # Mock GitHub and Anthropic APIs
    mock_github_api(respx_mock)
    mock_anthropic = mocker.patch(
        "anthropic.resources.messages.Messages.create",
        return_value=mocker.MagicMock(content=[mocker.MagicMock(text=FAKE_CLAUDE_RESPONSE)]),
        create=True,
    )

    analyzer = ClaudeAnalyzer()
    result = analyzer.analyze_repository(FAKE_GITHUB_URL)

    # Verify results
    assert result["name"] == "test-repo-pkg"
    assert result["runtime_type"] == "npx"
    assert result["install_command"] == "npm install"
    assert result["start_command"] == "npx start-server"
    assert len(result["env_variables"]) == 2
    assert result["env_variables"][0]["key"] == "API_KEY"
    assert result["env_variables"][0]["required"] is True
    assert result["env_variables"][1]["key"] == "OPTIONAL_FLAG"
    assert result["env_variables"][1]["required"] is False

    # Verify Claude was called
    assert mock_anthropic.called


def test_invalid_github_url():
    """Test analyzer with an invalid GitHub URL."""
    analyzer = ClaudeAnalyzer()
    with pytest.raises(ValueError, match="Invalid GitHub URL format"):
        analyzer.analyze_repository("htp:/invalid-url.com")


@respx.mock
def test_github_file_not_found(respx_mock, mocker):
    """Test when a key file like package.json is not found."""
    mock_github_api(respx_mock, pkg_json_status=404)
    mock_anthropic = mocker.patch("anthropic.resources.messages.Messages.create", create=True)

    analyzer = ClaudeAnalyzer()
    analyzer.analyze_repository(FAKE_GITHUB_URL)

    # Check that the prompt sent to Claude reflects the missing file
    assert mock_anthropic.called
    prompt = mock_anthropic.call_args[1]["messages"][0]["content"]
    assert '<file path="package.json">\nNot found.\n</file>' in prompt


def test_parse_claude_response():
    """Test the internal parsing logic for Claude's response."""
    analyzer = ClaudeAnalyzer()
    parsed = analyzer._parse_claude_response(FAKE_CLAUDE_RESPONSE)

    assert parsed["runtime_type"] == "npx"
    assert parsed["install_command"] == "npm install"
    assert parsed["start_command"] == "npx start-server"
    assert parsed["name"] == "test-repo-pkg"
    assert parsed["description"] == "A test repository for analysis."
    assert len(parsed["env_variables"]) == 2
    assert parsed["env_variables"][0] == {
        "key": "API_KEY",
        "description": "An API key",
        "required": True,
    }
    assert parsed["env_variables"][1] == {
        "key": "OPTIONAL_FLAG",
        "description": "An optional flag",
        "required": False,
    }
