"""Tests for CSRF protection in OAuth flows."""

import pytest
import time
from typing import Generator
from unittest.mock import patch

from mcp_anywhere.auth.csrf import CSRFProtection, CSRFState


class TestCSRFState:
    """Test CSRFState dataclass."""

    def test_csrf_state_creation(self) -> None:
        """CSRFState should be created with all required fields."""
        now = time.time()
        state = CSRFState(
            value="test_state_123",
            client_id="test_client",
            redirect_uri="http://localhost:3001/callback",
            created_at=now,
            expires_at=now + 600,
        )
        
        assert state.value == "test_state_123"
        assert state.client_id == "test_client"
        assert state.redirect_uri == "http://localhost:3001/callback"
        assert state.created_at == now
        assert state.expires_at == now + 600


class TestCSRFProtection:
    """Test CSRF protection implementation."""

    @pytest.fixture
    def csrf_protection(self) -> CSRFProtection:
        """Create CSRFProtection instance for testing."""
        return CSRFProtection(expiration_seconds=600)

    def test_initialization_with_default_expiration(self) -> None:
        """CSRFProtection should initialize with default 10 minute expiration."""
        csrf = CSRFProtection()
        
        assert csrf.expiration_seconds == 600
        assert csrf._states == {}

    def test_initialization_with_custom_expiration(self) -> None:
        """CSRFProtection should accept custom expiration time."""
        csrf = CSRFProtection(expiration_seconds=300)
        
        assert csrf.expiration_seconds == 300
        assert csrf._states == {}

    def test_generate_state_returns_valid_string(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """State generation should return a URL-safe string."""
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        state = csrf_protection.generate_state(client_id, redirect_uri)
        
        assert isinstance(state, str)
        assert len(state) > 32  # URL-safe base64 with 32 bytes should be longer
        # URL-safe characters only
        assert all(c.isalnum() or c in "-_" for c in state)

    def test_generate_state_stores_csrf_state(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """State generation should store CSRFState in internal dict."""
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        with patch('time.time', return_value=1000.0):
            state = csrf_protection.generate_state(client_id, redirect_uri)
        
        assert state in csrf_protection._states
        csrf_state = csrf_protection._states[state]
        assert csrf_state.client_id == client_id
        assert csrf_state.redirect_uri == redirect_uri
        assert csrf_state.created_at == 1000.0
        assert csrf_state.expires_at == 1600.0  # 1000 + 600

    def test_generate_state_creates_unique_values(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """Multiple state generations should create unique values."""
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        state1 = csrf_protection.generate_state(client_id, redirect_uri)
        state2 = csrf_protection.generate_state(client_id, redirect_uri)
        
        assert state1 != state2
        assert len(csrf_protection._states) == 2

    def test_validate_state_accepts_valid_state(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """Valid state with matching parameters should be accepted."""
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        state = csrf_protection.generate_state(client_id, redirect_uri)
        
        is_valid = csrf_protection.validate_state(state, client_id, redirect_uri)
        assert is_valid is True

    def test_validate_state_rejects_empty_state(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """Empty state should be rejected."""
        is_valid = csrf_protection.validate_state("", "client", "uri")
        assert is_valid is False

    def test_validate_state_rejects_none_state(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """None state should be rejected."""
        is_valid = csrf_protection.validate_state(None, "client", "uri")
        assert is_valid is False

    def test_validate_state_rejects_unknown_state(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """Unknown state value should be rejected."""
        is_valid = csrf_protection.validate_state(
            "unknown_state", "client", "uri"
        )
        assert is_valid is False

    def test_validate_state_rejects_wrong_client_id(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """State with wrong client ID should be rejected."""
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        state = csrf_protection.generate_state(client_id, redirect_uri)
        
        is_valid = csrf_protection.validate_state(
            state, "wrong_client", redirect_uri
        )
        assert is_valid is False

    def test_validate_state_rejects_wrong_redirect_uri(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """State with wrong redirect URI should be rejected."""
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        state = csrf_protection.generate_state(client_id, redirect_uri)
        
        is_valid = csrf_protection.validate_state(
            state, client_id, "http://evil.com/callback"
        )
        assert is_valid is False

    def test_validate_state_rejects_expired_state(self) -> None:
        """Expired state should be rejected and removed from storage."""
        csrf = CSRFProtection(expiration_seconds=1)
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        state = csrf.generate_state(client_id, redirect_uri)
        time.sleep(2)  # Wait for expiration
        
        is_valid = csrf.validate_state(state, client_id, redirect_uri)
        assert is_valid is False
        assert state not in csrf._states  # Should be removed

    def test_validate_state_is_one_time_use(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """State should only be valid once (consumed after validation)."""
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        state = csrf_protection.generate_state(client_id, redirect_uri)
        
        # First validation should succeed
        first_valid = csrf_protection.validate_state(state, client_id, redirect_uri)
        assert first_valid is True
        assert state not in csrf_protection._states  # Should be consumed
        
        # Second validation should fail
        second_valid = csrf_protection.validate_state(state, client_id, redirect_uri)
        assert second_valid is False

    def test_cleanup_expired_removes_old_states(self) -> None:
        """cleanup_expired should remove expired states only."""
        csrf = CSRFProtection(expiration_seconds=1)
        
        # Create states at different times
        with patch('time.time', return_value=1000.0):
            old_state = csrf.generate_state("client1", "uri1")
        
        with patch('time.time', return_value=1500.0):
            recent_state = csrf.generate_state("client2", "uri2")
        
        # Mock current time to be after first state expires
        with patch('time.time', return_value=1002.0):
            csrf.cleanup_expired()
        
        # Old state should be removed, recent state should remain
        assert old_state not in csrf._states
        assert recent_state in csrf._states

    def test_cleanup_expired_with_no_expired_states(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """cleanup_expired should not affect valid states."""
        client_id = "test_client"
        redirect_uri = "http://localhost:3001/callback"
        
        state = csrf_protection.generate_state(client_id, redirect_uri)
        original_count = len(csrf_protection._states)
        
        csrf_protection.cleanup_expired()
        
        assert len(csrf_protection._states) == original_count
        assert state in csrf_protection._states

    def test_generate_state_raises_value_error_for_empty_client_id(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """Generate state should raise ValueError for empty client_id."""
        with pytest.raises(ValueError, match="client_id cannot be empty"):
            csrf_protection.generate_state("", "http://localhost/callback")

    def test_generate_state_raises_value_error_for_empty_redirect_uri(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """Generate state should raise ValueError for empty redirect_uri."""
        with pytest.raises(ValueError, match="redirect_uri cannot be empty"):
            csrf_protection.generate_state("test_client", "")

    def test_get_active_state_count(
        self, csrf_protection: CSRFProtection
    ) -> None:
        """get_active_state_count should return correct count of active states."""
        assert csrf_protection.get_active_state_count() == 0
        
        # Generate some states
        csrf_protection.generate_state("client1", "uri1")
        csrf_protection.generate_state("client2", "uri2")
        
        assert csrf_protection.get_active_state_count() == 2
        
        # Validate one state (should be consumed)
        csrf_protection.validate_state(
            list(csrf_protection._states.keys())[0], "client1", "uri1"
        )
        
        assert csrf_protection.get_active_state_count() == 1