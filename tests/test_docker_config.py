"""Tests for Docker configuration and deployment setup"""

import pytest
import subprocess
import os
from pathlib import Path


class TestDockerConfiguration:
    """Test cases for Docker configuration"""

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists and is readable"""
        dockerfile_path = Path("Dockerfile")
        assert dockerfile_path.exists(), "Dockerfile not found"
        assert dockerfile_path.is_file(), "Dockerfile is not a file"

    def test_dockerfile_cmd_uses_new_entry_point(self):
        """Test that Dockerfile CMD uses the new entry point"""
        with open("Dockerfile", "r") as f:
            content = f.read()

        # Should use python -m mcp_router
        assert 'python", "-m", "mcp_router"' in content, "Dockerfile should use new entry point"

        # Should not use gunicorn directly
        assert "gunicorn" not in content, "Dockerfile should not use gunicorn directly"

    def test_fly_toml_exists(self):
        """Test that fly.toml exists and is configured correctly"""
        fly_toml_path = Path("fly.toml")
        assert fly_toml_path.exists(), "fly.toml not found"
        assert fly_toml_path.is_file(), "fly.toml is not a file"

    def test_fly_toml_single_service(self):
        """Test that fly.toml only has one service (no separate MCP port)"""
        with open("fly.toml", "r") as f:
            content = f.read()

        # Should not have port 8001 service anymore
        assert "8001" not in content, "fly.toml should not have separate MCP service on port 8001"

        # Should have main service on port 8000
        assert "internal_port = 8000" in content, "fly.toml should have main service on port 8000"

    def test_entry_point_script_exists(self):
        """Test that entrypoint.sh script exists"""
        entrypoint_path = Path("entrypoint.sh")
        assert entrypoint_path.exists(), "entrypoint.sh not found"
        assert entrypoint_path.is_file(), "entrypoint.sh is not a file"

    def test_python_entry_point_available(self):
        """Test that python -m mcp_router entry point is available"""
        # This tests that the package structure supports the entry point
        try:
            import mcp_router.__main__

            assert hasattr(mcp_router.__main__, "main"), "Entry point main function should exist"
        except ImportError as e:
            pytest.fail(f"Could not import entry point: {e}")
 