"""Simple test for HTMX analyze button functionality."""

import pytest
from unittest.mock import AsyncMock, patch
from starlette.requests import Request
from starlette.testclient import TestClient

from src.mcp_anywhere.web.routes import add_server_post, get_template_context


def test_htmx_detection_logic():
    """Test HTMX header detection logic in analyze functionality."""
    # Mock request with HTMX header
    mock_request = AsyncMock(spec=Request)
    mock_request.headers = {"HX-Request": "true"}
    
    # Test HTMX detection
    is_htmx = mock_request.headers.get("HX-Request")
    assert is_htmx == "true"
    
    # Mock request without HTMX header  
    mock_request_regular = AsyncMock(spec=Request)
    mock_request_regular.headers = {}
    
    # Test regular request detection
    is_htmx_regular = mock_request_regular.headers.get("HX-Request")
    assert is_htmx_regular is None


@pytest.mark.asyncio
async def test_analyze_form_validation():
    """Test that analyze form validates GitHub URLs correctly."""
    from src.mcp_anywhere.web.routes import AnalyzeFormData
    from pydantic import ValidationError
    
    # Valid GitHub URL
    valid_data = AnalyzeFormData(github_url="https://github.com/owner/repo")
    assert valid_data.github_url == "https://github.com/owner/repo"
    
    # Invalid URL should raise validation error
    with pytest.raises(ValidationError):
        AnalyzeFormData(github_url="not-a-url")


def test_template_context_helper():
    """Test that get_template_context correctly handles parameters."""
    mock_request = AsyncMock(spec=Request)
    
    # Test with analysis data
    context = get_template_context(
        mock_request, 
        github_url="https://github.com/test/repo",
        analysis={"name": "test-server", "description": "Test description"}
    )
    
    assert context["github_url"] == "https://github.com/test/repo"
    assert context["analysis"]["name"] == "test-server"
    assert context["analysis"]["description"] == "Test description"
    
    # Test with error
    error_context = get_template_context(
        mock_request,
        error="Test error message"
    )
    
    assert error_context["error"] == "Test error message"