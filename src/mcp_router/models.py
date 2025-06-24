"""Database models for MCP Router"""
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class MCPServer(db.Model):
    """Model representing an MCP server configuration"""
    __tablename__ = 'mcp_servers'
    
    id = db.Column(db.String(32), primary_key=True, default=lambda: os.urandom(16).hex())
    name = db.Column(db.String(100), unique=True, nullable=False)
    github_url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    runtime_type = db.Column(db.String(20), nullable=False)
    install_command = db.Column(db.String(500), nullable=False, default='')
    start_command = db.Column(db.String(500), nullable=False)
    _env_variables = db.Column('env_variables', db.Text, default='[]')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    @property
    def env_variables(self) -> List[Dict[str, Any]]:
        """Get environment variables as a list of dictionaries
        
        Returns:
            List of environment variable configurations
        """
        return json.loads(self._env_variables)
    
    @env_variables.setter
    def env_variables(self, value: List[Dict[str, Any]]) -> None:
        """Set environment variables from a list of dictionaries
        
        Args:
            value: List of environment variable configurations
        """
        self._env_variables = json.dumps(value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary representation
        
        Returns:
            Dictionary representation of the server
        """
        return {
            'id': self.id,
            'name': self.name,
            'github_url': self.github_url,
            'description': self.description,
            'runtime_type': self.runtime_type,
            'install_command': self.install_command,
            'start_command': self.start_command,
            'env_variables': self.env_variables,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat()
        }
    
    def __repr__(self) -> str:
        """String representation of the model"""
        return f'<MCPServer {self.name}>'


# Helper functions for database access.
# These are synchronous and should be called from within a thread executor
# in an async context to avoid blocking the event loop.
def get_active_servers() -> List[MCPServer]:
    """Get all active servers
    
    Returns:
        List of active MCP server configurations
    """
    return MCPServer.query.filter_by(is_active=True).all()


def get_server_by_id(server_id: str) -> Optional[MCPServer]:
    """Get server by ID
    
    Args:
        server_id: The server ID to look up
        
    Returns:
        MCPServer instance or None if not found
    """
    return MCPServer.query.get(server_id)


def init_db(app) -> None:
    """Initialize the database with the Flask app
    
    Args:
        app: Flask application instance
    """
    db.init_app(app)
    with app.app_context():
        db.create_all() 