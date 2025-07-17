"""Tests for dynamic authentication middleware"""

import pytest
from unittest.mock import patch
from mcp_router.asgi import get_cached_auth_type, clear_auth_type_cache
from mcp_router.models import db, MCPServerStatus, get_auth_type, set_auth_type


class TestDynamicAuth:
    """Test dynamic authentication functionality"""

    def test_get_auth_type_from_database(self, app):
        """Test getting auth type from database"""
        with app.app_context():
            # Create status record with oauth
            status = MCPServerStatus(transport="http", status="running", auth_type="oauth")
            db.session.add(status)
            db.session.commit()

            assert get_auth_type() == "oauth"

    def test_get_auth_type_fallback_to_config(self, app):
        """Test fallback to config when no database record"""
        with app.app_context():
            # Ensure no status record exists
            MCPServerStatus.query.delete()
            db.session.commit()

            with patch("mcp_router.config.Config.MCP_AUTH_TYPE", "oauth"):
                assert get_auth_type() == "oauth"

            with patch("mcp_router.config.Config.MCP_AUTH_TYPE", "api_key"):
                assert get_auth_type() == "api_key"

    def test_set_auth_type_valid_values(self, app):
        """Test setting valid auth type values"""
        with app.app_context():
            # Test setting oauth
            set_auth_type("oauth")
            assert get_auth_type() == "oauth"

            # Test setting api_key
            set_auth_type("api_key")
            assert get_auth_type() == "api_key"

    def test_set_auth_type_invalid_value(self, app):
        """Test setting invalid auth type raises ValueError"""
        with app.app_context():
            with pytest.raises(ValueError, match="Invalid auth_type 'invalid'"):
                set_auth_type("invalid")

    def test_cached_auth_type_performance(self, app):
        """Test auth type caching functionality"""
        with app.app_context():
            # Clear cache first
            clear_auth_type_cache()

            # Create status record
            status = MCPServerStatus(transport="http", status="running", auth_type="oauth")
            db.session.add(status)
            db.session.commit()

            # First call should hit database
            with patch("mcp_router.models.get_auth_type") as mock_get_auth:
                mock_get_auth.return_value = "oauth"
                get_cached_auth_type()
                assert mock_get_auth.call_count == 1

                # Second call should use cache
                get_cached_auth_type()
                assert mock_get_auth.call_count == 1  # No additional calls

    def test_cache_expiration(self, app):
        """Test cache expiration after TTL"""
        with app.app_context():
            clear_auth_type_cache()

            # Mock time to control cache expiration
            with patch("time.time") as mock_time:
                mock_time.return_value = 1000

                with patch("mcp_router.models.get_auth_type") as mock_get_auth:
                    mock_get_auth.return_value = "oauth"

                    # First call
                    get_cached_auth_type()
                    assert mock_get_auth.call_count == 1

                    # Move time forward but within TTL
                    mock_time.return_value = 1020  # 20 seconds later
                    get_cached_auth_type()
                    assert mock_get_auth.call_count == 1  # Still cached

                    # Move time past TTL
                    mock_time.return_value = 1040  # 40 seconds later (>30 TTL)
                    get_cached_auth_type()
                    assert mock_get_auth.call_count == 2  # Cache expired

    def test_clear_auth_type_cache(self, app):
        """Test cache clearing functionality"""
        with app.app_context():
            # Prime the cache
            with patch("mcp_router.models.get_auth_type") as mock_get_auth:
                mock_get_auth.return_value = "oauth"
                get_cached_auth_type()
                assert mock_get_auth.call_count == 1

                # Clear cache
                clear_auth_type_cache()

                # Next call should hit database again
                get_cached_auth_type()
                assert mock_get_auth.call_count == 2

    def test_cached_auth_type_database_error_fallback(self, app):
        """Test fallback to config when database unavailable"""
        clear_auth_type_cache()

        with patch("mcp_router.models.get_auth_type") as mock_get_auth:
            mock_get_auth.side_effect = Exception("Database error")

            with patch("mcp_router.config.Config.MCP_AUTH_TYPE", "oauth"):
                result = get_cached_auth_type()
                assert result == "oauth"

            with patch("mcp_router.config.Config.MCP_AUTH_TYPE", "api_key"):
                result = get_cached_auth_type()
                assert result == "api_key"

    def test_auth_type_switching_mid_request(self, app):
        """Test auth type switching takes effect on subsequent requests"""
        with app.app_context():
            # Set initial auth type
            set_auth_type("api_key")
            assert get_auth_type() == "api_key"

            # Clear cache and switch
            clear_auth_type_cache()
            set_auth_type("oauth")
            assert get_auth_type() == "oauth"

    def test_concurrent_auth_type_access(self, app):
        """Test thread safety of auth type caching"""
        import threading
        import queue

        with app.app_context():
            set_auth_type("oauth")
            clear_auth_type_cache()

            results = queue.Queue()

            def get_auth_worker():
                try:
                    with app.app_context():
                        result = get_cached_auth_type()
                        results.put(result)
                except Exception as e:
                    results.put(f"Error: {e}")

            # Start multiple threads
            threads = [threading.Thread(target=get_auth_worker) for _ in range(5)]
            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join()

            # All should return same result
            auth_types = []
            while not results.empty():
                auth_types.append(results.get())

            assert len(auth_types) == 5
            assert all(auth_type == "oauth" for auth_type in auth_types)
