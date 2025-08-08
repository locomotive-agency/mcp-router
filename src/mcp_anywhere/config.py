"""Configuration settings for MCP Anywhere"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Define the base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Define the data directory (configurable via environment variable)
_data_dir_path = os.environ.get("DATA_DIR", ".data")
# If it's a relative path, make it relative to BASE_DIR
if not os.path.isabs(_data_dir_path):
    DATA_DIR = BASE_DIR / _data_dir_path
else:
    DATA_DIR = Path(_data_dir_path)
DATA_DIR.mkdir(exist_ok=True)


class Config:
    """Configuration class"""

    # Data directory setting
    DATA_DIR = DATA_DIR

    # Session settings
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    WEB_PORT = int(os.environ.get("WEB_PORT", "8000"))

    # JWT settings for OAuth
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)

    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DATA_DIR / 'mcp_anywhere.db'}"
    )

    # External API keys
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

    # Claude settings
    ANTHROPIC_MODEL_NAME = os.environ.get(
        "ANTHROPIC_MODEL_NAME", "claude-sonnet-4-20250514"
    )

    # MCP Server settings
    # Base path users configure (may or may not include leading/trailing slashes)
    _RAW_MCP_PATH = os.environ.get("MCP_PATH", "/mcp")

    # Normalize to always have a single leading slash and no trailing slash
    if not _RAW_MCP_PATH.startswith("/"):
        _RAW_MCP_PATH = f"/{_RAW_MCP_PATH}"
    MCP_PATH = _RAW_MCP_PATH.rstrip("/") or "/"

    # Derived helpers:
    # - MCP_PATH_MOUNT: non-trailing variant for Starlette mount (e.g. "/mcp")
    # - MCP_PATH_PREFIX: trailing-slash variant for URLs (e.g. "/mcp/")
    MCP_PATH_MOUNT = MCP_PATH
    MCP_PATH_PREFIX = MCP_PATH if MCP_PATH.endswith("/") else (MCP_PATH + "/")

    # Server URL - configurable for different environments
    SERVER_URL = os.environ.get(
        "SERVER_URL", f"http://localhost:{os.environ.get('WEB_PORT', '8000')}"
    )

    # Logging settings
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FORMAT = os.environ.get("LOG_FORMAT", None)  # Use default if not specified
    LOG_FILE = os.environ.get("LOG_FILE", None)  # No file logging by default
    LOG_JSON = os.environ.get("LOG_JSON", "false").lower() in ("true", "1", "yes")

    # Container settings
    DOCKER_HOST = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")
    MCP_PYTHON_IMAGE = os.environ.get("MCP_PYTHON_IMAGE", "python:3.11-slim")
    MCP_NODE_IMAGE = os.environ.get("MCP_NODE_IMAGE", "node:20-slim")
    DOCKER_TIMEOUT = int(os.environ.get("DOCKER_TIMEOUT", "300"))  # 5 minutes default
    DEFAULT_SERVERS_FILE = os.environ.get(
        "DEFAULT_SERVERS_FILE", "default_servers.json"
    )
