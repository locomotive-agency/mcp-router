"""Database models for MCP Router"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON

db = SQLAlchemy()


class MCPServer(db.Model):
    """Model for MCP server configurations"""
    __tablename__ = 'mcp_servers'
    
    id = db.Column(db.String(32), primary_key=True, default=lambda: generate_id())
    name = db.Column(db.String(100), unique=True, nullable=False)
    github_url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    runtime_type = db.Column(db.String(20), nullable=False)  # npx, uvx, docker
    install_command = db.Column(db.Text, nullable=False, default='')
    start_command = db.Column(db.Text, nullable=False)
    env_variables = db.Column(JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<MCPServer {self.name}>'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
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
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class MCPServerStatus(db.Model):
    """Model to track MCP server runtime status"""
    __tablename__ = 'mcp_server_status'
    
    id = db.Column(db.Integer, primary_key=True)
    transport = db.Column(db.String(20), nullable=False)  # stdio, http
    status = db.Column(db.String(20), nullable=False, default='stopped')
    pid = db.Column(db.Integer)  # Process ID if running
    port = db.Column(db.Integer)  # Port if HTTP
    host = db.Column(db.String(100))  # Host if HTTP
    path = db.Column(db.String(100))  # Path if HTTP
    api_key = db.Column(db.String(100))  # API key if HTTP (stored for display, not secure storage)
    started_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert status to dictionary for API responses"""
        return {
            'id': self.id,
            'transport': self.transport,
            'status': self.status,
            'pid': self.pid,
            'port': self.port,
            'host': self.host,
            'path': self.path,
            'api_key': '***' if self.api_key else None,  # Don't expose full API key
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'error_message': self.error_message
        }


def generate_id() -> str:
    """Generate a unique ID for servers"""
    import uuid
    return uuid.uuid4().hex[:32]


def init_db(app):
    """Initialize database with app context"""
    db.init_app(app)
    with app.app_context():
        db.create_all()


def get_server_by_id(server_id: str) -> Optional[MCPServer]:
    """Get server by ID"""
    return MCPServer.query.get(server_id)


def get_active_servers() -> List[MCPServer]:
    """Get all active servers"""
    return MCPServer.query.filter_by(is_active=True).all()


def get_server_status() -> Optional[MCPServerStatus]:
    """Get current MCP server status"""
    return MCPServerStatus.query.first()


def update_server_status(transport: str, status: str, **kwargs) -> MCPServerStatus:
    """Update or create server status"""
    server_status = MCPServerStatus.query.first()
    if not server_status:
        server_status = MCPServerStatus(transport=transport, status=status)
        db.session.add(server_status)
    else:
        server_status.transport = transport
        server_status.status = status
    
    # Update additional fields
    for key, value in kwargs.items():
        if hasattr(server_status, key):
            setattr(server_status, key, value)
    
    db.session.commit()
    return server_status 