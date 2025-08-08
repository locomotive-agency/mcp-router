from datetime import datetime

import pytest

from mcp_anywhere.auth.models import OAuth2Client, User


@pytest.mark.asyncio
async def test_user_password_verification():
    """Test user password verification without database operations."""
    user = User(username="testuser")
    user.set_password("secret123")

    assert user.check_password("secret123") is True
    assert user.check_password("wrongpassword") is False


def test_user_to_dict():
    """Test user to_dict method."""
    user = User(username="testuser")
    user.id = 1
    user.created_at = datetime(2023, 1, 1, 12, 0, 0)

    user_dict = user.to_dict()

    assert user_dict["id"] == 1
    assert user_dict["username"] == "testuser"
    assert user_dict["created_at"] == "2023-01-01T12:00:00"


def test_oauth2_client_to_dict():
    """Test OAuth2Client to_dict method."""
    client = OAuth2Client(
        client_id="test_client",
        client_secret="secret123",
        redirect_uri="http://localhost:3000/auth/callback",
        scope="read write",
    )
    client.id = 1
    client.created_at = datetime(2023, 1, 1, 12, 0, 0)

    client_dict = client.to_dict()

    assert client_dict["id"] == 1
    assert client_dict["client_id"] == "test_client"
    assert client_dict["redirect_uri"] == "http://localhost:3000/auth/callback"
    assert client_dict["scope"] == "read write"
    assert client_dict["created_at"] == "2023-01-01T12:00:00"
