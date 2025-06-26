"""Configuration settings for MCP Router"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Define the base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Define the data directory
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)


class Config:
    """Base configuration class"""
    # Flask settings
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production'))
    FLASK_PORT = int(os.environ.get('FLASK_PORT', '8000'))
    
    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f"sqlite:///{DATA_DIR / 'mcp_router.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # External API keys
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    
    # MCP Server settings
    MCP_TRANSPORT = os.environ.get('MCP_TRANSPORT', 'stdio')
    MCP_HOST = os.environ.get('MCP_HOST', '127.0.0.1')
    MCP_PORT = int(os.environ.get('MCP_PORT', '8001'))
    MCP_PATH = os.environ.get('MCP_PATH', '/mcp')
    MCP_SSE_PATH = os.environ.get('MCP_SSE_PATH', '/sse')
    MCP_LOG_LEVEL = os.environ.get('MCP_LOG_LEVEL', 'info')
    MCP_API_KEY = os.environ.get('MCP_API_KEY')
    
    # Container settings
    DOCKER_HOST = os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock')
    MCP_PYTHON_IMAGE = os.environ.get('MCP_PYTHON_IMAGE', 'python:3.11-slim')
    MCP_NODE_IMAGE = os.environ.get('MCP_NODE_IMAGE', 'node:20-slim')
    
    # Application settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    
    # Debug mode (should be False in production)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'yes']


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get configuration based on environment"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default']) 