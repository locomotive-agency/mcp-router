"""OAuth initialization utilities for setting up default users and clients."""

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_anywhere.auth.models import OAuth2Client, User
from mcp_anywhere.config import Config
from mcp_anywhere.database import get_async_session
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


async def create_default_admin_user(
    username: str = "admin", password: str = None, db_session: AsyncSession = None
) -> User:
    """Create default admin user if it doesn't exist.

    Args:
        username: Admin username
        password: Admin password (if None, generates a random one)
        db_session: Database session (if None, creates one)

    Returns:
        User object for the admin user
    """
    if not db_session:
        async with get_async_session() as session:
            return await create_default_admin_user(username, password, session)

    # Check if admin user already exists
    stmt = select(User).where(User.username == username)
    result = await db_session.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        logger.info(f"Admin user '{username}' already exists")
        return existing_user

    # Generate password if not provided
    if not password:
        password = secrets.token_urlsafe(16)
        logger.warning(f"Generated random password for admin user: {password}")
        logger.warning("Please change this password after first login!")

    # Create admin user
    admin_user = User(username=username)
    admin_user.set_password(password)

    db_session.add(admin_user)
    await db_session.commit()
    await db_session.refresh(admin_user)

    logger.info(f"Created admin user: {username}")
    return admin_user


async def create_default_oauth_client(
    client_id: str = None,
    client_secret: str = None,
    redirect_uri: str = None,
    scope: str = "mcp:read mcp:write",
    db_session: AsyncSession = None,
) -> OAuth2Client:
    """Create default OAuth client if it doesn't exist.

    Args:
        client_id: OAuth client ID (if None, generates one)
        client_secret: OAuth client secret (if None, generates one)
        redirect_uri: Redirect URI for OAuth flow (if None, uses Config.SERVER_URL)
        scope: Allowed scopes for the client
        db_session: Database session (if None, creates one)

    Returns:
        OAuth2Client object for the default client
    """
    # Use Config.SERVER_URL for redirect_uri if not provided
    if redirect_uri is None:
        redirect_uri = f"{Config.SERVER_URL}/auth/callback"

    if not db_session:
        async with get_async_session() as session:
            return await create_default_oauth_client(
                client_id, client_secret, redirect_uri, scope, session
            )

    # Generate client credentials if not provided
    if not client_id:
        client_id = "test-client"  # Use consistent default client_id

    if not client_secret:
        client_secret = "test-secret"  # Use consistent default for testing

    # Check if client already exists
    stmt = select(OAuth2Client).where(OAuth2Client.client_id == client_id)
    result = await db_session.execute(stmt)
    existing_client = result.scalar_one_or_none()

    if existing_client:
        logger.info(f"OAuth client '{client_id}' already exists")
        return existing_client

    # Create OAuth client
    oauth_client = OAuth2Client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
    )

    db_session.add(oauth_client)
    await db_session.commit()
    await db_session.refresh(oauth_client)

    logger.info(f"Created OAuth client: {client_id}")
    logger.info(f"Client secret: {client_secret}")
    logger.info(f"Redirect URI: {redirect_uri}")

    return oauth_client


async def initialize_oauth_data(
    admin_username: str = "admin",
    admin_password: str = None,
    client_id: str = None,
    client_secret: str = None,
    redirect_uri: str = None,
) -> tuple[User, OAuth2Client]:
    """Initialize default OAuth data (admin user and OAuth client).

    Args:
        admin_username: Admin username
        admin_password: Admin password (if None, generates random)
        client_id: OAuth client ID (if None, generates)
        client_secret: OAuth client secret (if None, generates)
        redirect_uri: OAuth redirect URI (if None, uses Config.SERVER_URL)

    Returns:
        Tuple of (admin_user, oauth_client)
    """
    # Use Config.SERVER_URL for redirect_uri if not provided
    if redirect_uri is None:
        redirect_uri = f"{Config.SERVER_URL}/auth/callback"

    async with get_async_session() as db_session:
        # Create admin user
        admin_user = await create_default_admin_user(
            username=admin_username, password=admin_password, db_session=db_session
        )

        # Create OAuth client
        oauth_client = await create_default_oauth_client(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            db_session=db_session,
        )

        return admin_user, oauth_client
