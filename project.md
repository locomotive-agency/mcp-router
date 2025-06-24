# MCP Router MVP Development Plan

## Executive Summary

MCP Router is a Python-based tool that acts as a unified gateway for multiple MCP (Model Context Protocol) servers. It provides a web UI for managing servers, analyzes GitHub repositories using Claude, and dynamically spawns containerized environments on-demand.

**MVP Timeline:** 4 weeks, 1 developer  
**Core Stack:** Flask + htmx, FastMCP 2.x, llm-sandbox, SQLite  
**Transports:** stdio (local) and HTTP (remote) only

## Core MVP Features

1. **Web UI** - Flask with server-side rendering for server management
2. **Claude Analyzer** - Automated GitHub repository analysis
3. **Container Management** - npx, uvx, and docker runtime support
4. **MCP Router** - Dynamic tool registration via FastMCP
5. **Python Sandbox** - Built-in data science environment
6. **Transport Support** - stdio and HTTP only (skip deprecated SSE)
7. **Claude Desktop Integration** - Local configuration generator

## System Architecture

```
┌─────────────────┐     ┌─────────────────┐
│  Claude Desktop │     │   Web Browser   │
│   (stdio)       │     │   (Admin UI)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │                       │ HTTP
         │                       │
┌────────┴───────────────────────┴────────┐
│           MCP Router Service            │
│  ┌─────────────┐  ┌──────────────┐     │
│  │    Flask    │  │   FastMCP    │     │
│  │  Web Server │  │   Router     │     │
│  └─────────────┘  └──────────────┘     │
│  ┌─────────────┐  ┌──────────────┐     │
│  │   Claude    │  │  Container   │     │
│  │  Analyzer   │  │  Manager     │     │
│  └─────────────┘  └──────────────┘     │
└─────────────────────────────────────────┘
                    │
         ┌──────────┼──────────┐
         │          │          │
    ┌────▼───┐ ┌───▼───┐ ┌───▼────┐
    │  NPX   │ │  UVX  │ │ Docker │
    └────────┘ └───────┘ └────────┘
```

## Technology Stack

### Backend
- **Python 3.11+** - Core language
- **Flask 2.3+** - Web framework
- **FastMCP 2.x** - MCP protocol implementation
- **llm-sandbox** - Container runtime management
- **SQLite + SQLAlchemy** - Database
- **Flask-WTF** - Form handling and CSRF
- **anthropic** - Claude API integration
- **httpx** - Async HTTP client

### Frontend (Server-Side Rendered)
- **Jinja2** - HTML templating
- **htmx 1.9+** - Dynamic updates without JavaScript
- **TailwindCSS** - Styling via CDN
- **Minimal vanilla JS** - Progressive enhancement only

## Database Schema

```sql
-- Single table for MVP simplicity
CREATE TABLE mcp_servers (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL UNIQUE,
    github_url TEXT NOT NULL,
    description TEXT,
    runtime_type TEXT NOT NULL CHECK(runtime_type IN ('npx', 'uvx', 'docker')),
    install_command TEXT NOT NULL,
    start_command TEXT NOT NULL,
    env_variables JSON NOT NULL DEFAULT '[]',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## Project Structure

A standard Python project structure is used for maintainability and deployability.

```
mcp-router/
├── .gitignore
├── .env.example
├── data/
│   └── .gitignore           # Keeps data dir in git, ignores contents
├── docker-compose.yml
├── Dockerfile
├── project.md
├── pyproject.toml           # Project definition and dependencies
├── README.md
├── src/
│   └── mcp_router/
│       ├── __init__.py
│       ├── __main__.py        # Main entry point for `python -m mcp_router`
│       ├── app.py
│       ├── claude_analyzer.py # To be implemented
│       ├── config.py
│       ├── container_manager.py # To be implemented
│       ├── forms.py
│       ├── models.py
│       ├── server.py        # To be implemented
│       ├── static/            # For CSS, JS, images
│       └── templates/
│           ├── *.html
│           └── servers/*.html
└── tests/
    ├── __init__.py
    └── test_models.py
```

## Core Implementation

### 1. FastMCP Server with Python Sandbox (server.py)

```python
import asyncio
import logging
from fastmcp import FastMCP
from llm_sandbox import SandboxSession
from container_manager import ContainerManager
from models import get_active_servers

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    name="MCP-Router",
    instructions="""This router provides access to multiple MCP servers and a Python sandbox.
    Use 'python_sandbox' for data analysis with pandas, numpy, matplotlib, etc.
    Other tools are dynamically loaded from configured servers."""
)

# Built-in Python sandbox tool
@mcp.tool
def python_sandbox(code: str, libraries: list[str] = None) -> dict:
    """Execute Python code in a secure sandbox with data science libraries.
    
    Args:
        code: Python code to execute
        libraries: Additional pip packages to install (e.g., ["pandas", "scikit-learn"])
    
    Returns:
        Dictionary with stdout, stderr, and exit_code
    """
    log.info(f"Executing Python code with libraries: {libraries}")
    
    # Default libraries always available
    default_libs = ["pandas", "numpy", "matplotlib", "seaborn", "scipy"]
    
    try:
        with SandboxSession(lang="python", timeout=30) as session:
            # Install default + requested libraries
            all_libs = default_libs + (libraries or [])
            if all_libs:
                install_cmd = f"pip install --no-cache-dir {' '.join(all_libs)}"
                result = session.execute_command(install_cmd)
                if result.exit_code != 0:
                    return {
                        "status": "error",
                        "message": "Failed to install libraries",
                        "stderr": result.stderr
                    }
            
            # Execute code
            result = session.run(code)
            
            return {
                "status": "success" if result.exit_code == 0 else "error",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code
            }
    except Exception as e:
        log.error(f"Sandbox error: {e}")
        return {"status": "error", "message": str(e)}

# Container manager for dynamic servers
container_manager = ContainerManager()

async def register_server_tools():
    """Dynamically register tools from database servers"""
    servers = await get_active_servers()
    
    for server in servers:
        # Create a tool function for each server
        async def server_tool(**kwargs):
            """Dynamic tool that proxies to containerized server"""
            return await container_manager.execute_server_tool(
                server_id=server.id,
                tool_params=kwargs
            )
        
        # Register with unique name
        tool_name = f"{server.name}_tool"
        server_tool.__name__ = tool_name
        server_tool.__doc__ = f"Tool from {server.name}: {server.description}"
        
        mcp.tool()(server_tool)

# Run server
if __name__ == "__main__":
    # Register dynamic tools on startup
    asyncio.run(register_server_tools())
    
    # Run with stdio for Claude Desktop
    mcp.run(transport="stdio")
```

### 2. Container Manager with Async Bridge (container_manager.py)

```python
import asyncio
from typing import Dict, Any
from llm_sandbox import SandboxSession
from models import get_server_by_id

class ContainerManager:
    """Manages container lifecycle with async bridge for llm-sandbox"""
    
    def __init__(self):
        self.active_sessions = {}
    
    async def execute_server_tool(self, server_id: str, tool_params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool in containerized MCP server"""
        server = await get_server_by_id(server_id)
        if not server:
            return {"error": "Server not found"}
        
        # Bridge sync llm-sandbox to async
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            self._run_server_sync,
            server,
            tool_params
        )
        return result
    
    def _run_server_sync(self, server, tool_params: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous execution for llm-sandbox"""
        try:
            # Create appropriate sandbox based on runtime
            if server.runtime_type == "npx":
                session = SandboxSession(
                    lang="javascript",
                    runtime="node",
                    timeout=30,
                    env_vars=self._get_env_vars(server)
                )
            elif server.runtime_type == "uvx":
                session = SandboxSession(
                    lang="python",
                    timeout=30,
                    env_vars=self._get_env_vars(server)
                )
            elif server.runtime_type == "docker":
                session = SandboxSession(
                    image=server.docker_image,
                    timeout=30,
                    env_vars=self._get_env_vars(server)
                )
            
            with session:
                # Install/setup if needed
                if server.install_command:
                    install_result = session.execute_command(server.install_command)
                    if install_result.exit_code != 0:
                        return {
                            "error": "Installation failed",
                            "stderr": install_result.stderr
                        }
                
                # Start MCP server
                start_result = session.execute_command(server.start_command)
                
                # Forward tool call via stdio
                # This is simplified - actual implementation would handle MCP protocol
                return {
                    "stdout": start_result.stdout,
                    "stderr": start_result.stderr,
                    "exit_code": start_result.exit_code
                }
                
        except Exception as e:
            return {"error": str(e)}
    
    def _get_env_vars(self, server) -> Dict[str, str]:
        """Extract environment variables from server config"""
        env_vars = {}
        for env in server.env_variables:
            if env.get("value"):
                env_vars[env["key"]] = env["value"]
        return env_vars
```

### 3. Flask Web Application (app.py)

```python
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField
from wtforms.validators import DataRequired, URL
from claude_analyzer import ClaudeAnalyzer
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mcp_router.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Import models after db initialization
from models import MCPServer

# Initialize database
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    """Dashboard showing all servers"""
    servers = MCPServer.query.filter_by(is_active=True).all()
    return render_template('index.html', servers=servers)

@app.route('/servers/add', methods=['GET', 'POST'])
def add_server():
    """Add new server with GitHub analysis"""
    if request.method == 'POST':
        # Handle analyze button
        if 'analyze' in request.form:
            github_url = request.form.get('github_url')
            if github_url:
                analyzer = ClaudeAnalyzer()
                analysis = analyzer.analyze_repository(github_url)
                return render_template('servers/add.html', 
                                     github_url=github_url,
                                     analysis=analysis)
        
        # Handle save button
        elif 'save' in request.form:
            server = MCPServer(
                name=request.form.get('name'),
                github_url=request.form.get('github_url'),
                description=request.form.get('description'),
                runtime_type=request.form.get('runtime_type'),
                install_command=request.form.get('install_command'),
                start_command=request.form.get('start_command')
            )
            
            # Add environment variables
            env_vars = []
            for key in request.form.getlist('env_keys[]'):
                if key:
                    env_vars.append({
                        'key': key,
                        'value': request.form.get(f'env_value_{key}', ''),
                        'description': request.form.get(f'env_desc_{key}', '')
                    })
            server.env_variables = env_vars
            
            db.session.add(server)
            db.session.commit()
            
            flash(f'Server "{server.name}" added successfully!', 'success')
            return redirect(url_for('index'))
    
    return render_template('servers/add.html')

@app.route('/servers/<server_id>')
def server_detail(server_id):
    """Show server details"""
    server = MCPServer.query.get_or_404(server_id)
    return render_template('servers/detail.html', server=server)

@app.route('/api/servers/<server_id>/test', methods=['POST'])
def test_server(server_id):
    """Test server connection (htmx endpoint)"""
    server = MCPServer.query.get_or_404(server_id)
    
    # Simple test - check if server config is valid
    # In production, would actually try to spawn container
    is_valid = bool(server.start_command and server.runtime_type)
    
    if is_valid:
        return '<div class="text-green-600">✓ Configuration valid</div>'
    else:
        return '<div class="text-red-600">✗ Invalid configuration</div>'

@app.route('/config/claude-desktop')
def claude_desktop_config():
    """Generate Claude Desktop configuration"""
    config = {
        "mcpServers": {
            "mcp-router": {
                "command": "python",
                "args": ["server.py"],
                "env": {
                    "PYTHONPATH": os.getcwd()
                }
            }
        }
    }
    return jsonify(config)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

### 4. Claude Repository Analyzer (claude_analyzer.py)

```python
import os
import re
import httpx
from anthropic import Anthropic
from typing import Dict, Any

class ClaudeAnalyzer:
    """Analyzes GitHub repositories to extract MCP server configuration"""
    
    def __init__(self):
        self.client = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        self.github_token = os.environ.get('GITHUB_TOKEN')
    
    def analyze_repository(self, github_url: str) -> Dict[str, Any]:
        """Analyze GitHub repository and return configuration"""
        # Extract owner/repo from URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)', github_url)
        if not match:
            return {"error": "Invalid GitHub URL"}
        
        owner, repo = match.groups()
        
        # Fetch repository files
        readme = self._fetch_file(owner, repo, 'README.md')
        package_json = self._fetch_file(owner, repo, 'package.json')
        pyproject = self._fetch_file(owner, repo, 'pyproject.toml')
        
        # Prepare prompt for Claude
        prompt = f"""Analyze this MCP server repository and extract configuration.

Repository: {github_url}

README.md:
{readme or 'Not found'}

package.json:
{package_json or 'Not found'}

pyproject.toml:
{pyproject or 'Not found'}

Extract:
1. Runtime type: 'npx' for Node.js, 'uvx' for Python, 'docker' if Dockerfile exists
2. Install command (e.g., "npm install" or "pip install -e .")
3. Start command (e.g., "npx mcp-server" or "python -m mcp_server")
4. Required environment variables (API keys, tokens, etc.)
5. Brief description of what this MCP server does
6. Server name (from package name or reasonable default)

Respond in this exact format:
RUNTIME: [npx|uvx|docker]
INSTALL: [command or "none"]
START: [command]
NAME: [server name]
DESCRIPTION: [one line description]
ENV_VARS:
- KEY: [key name], DESC: [description], REQUIRED: [true|false]
"""
        
        # Get Claude's analysis
        response = self.client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response
        return self._parse_claude_response(response.content[0].text)
    
    def _fetch_file(self, owner: str, repo: str, path: str) -> str:
        """Fetch file content from GitHub"""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {}
        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'
        
        try:
            response = httpx.get(url, headers=headers)
            if response.status_code == 200:
                import base64
                content = response.json()['content']
                return base64.b64decode(content).decode('utf-8')
        except:
            pass
        return None
    
    def _parse_claude_response(self, text: str) -> Dict[str, Any]:
        """Parse Claude's structured response"""
        result = {
            'runtime_type': 'docker',
            'install_command': '',
            'start_command': '',
            'name': 'unnamed-server',
            'description': 'MCP server',
            'env_variables': []
        }
        
        # Extract fields
        for line in text.split('\n'):
            if line.startswith('RUNTIME:'):
                result['runtime_type'] = line.split(':', 1)[1].strip()
            elif line.startswith('INSTALL:'):
                cmd = line.split(':', 1)[1].strip()
                if cmd.lower() != 'none':
                    result['install_command'] = cmd
            elif line.startswith('START:'):
                result['start_command'] = line.split(':', 1)[1].strip()
            elif line.startswith('NAME:'):
                result['name'] = line.split(':', 1)[1].strip()
            elif line.startswith('DESCRIPTION:'):
                result['description'] = line.split(':', 1)[1].strip()
            elif line.startswith('- KEY:'):
                # Parse environment variable
                parts = line.split(',')
                key = parts[0].split(':', 1)[1].strip()
                desc = parts[1].split(':', 1)[1].strip() if len(parts) > 1 else ''
                required = 'true' in parts[2] if len(parts) > 2 else True
                result['env_variables'].append({
                    'key': key,
                    'description': desc,
                    'required': required
                })
        
        return result
```

### 5. Database Models (models.py)

```python
from flask_sqlalchemy import SQLAlchemy
import json
from datetime import datetime

db = SQLAlchemy()

class MCPServer(db.Model):
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
    def env_variables(self):
        return json.loads(self._env_variables)
    
    @env_variables.setter
    def env_variables(self, value):
        self._env_variables = json.dumps(value)
    
    def to_dict(self):
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

# Helper functions for async compatibility
async def get_active_servers():
    """Get all active servers (async wrapper)"""
    return MCPServer.query.filter_by(is_active=True).all()

async def get_server_by_id(server_id: str):
    """Get server by ID (async wrapper)"""
    return MCPServer.query.get(server_id)
```

### 6. HTML Templates

#### Base Template (templates/base.html)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}MCP Router{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <meta name="csrf-token" content="{{ csrf_token() }}">
</head>
<body class="bg-gray-50">
    <nav class="bg-white shadow">
        <div class="max-w-6xl mx-auto px-4">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <h1 class="text-xl font-semibold">MCP Router</h1>
                </div>
                <div class="flex items-center space-x-4">
                    <a href="/" class="text-gray-700 hover:text-gray-900">Servers</a>
                    <a href="/servers/add" class="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
                        Add Server
                    </a>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-6xl mx-auto py-6 px-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="mb-4 p-4 rounded-md {% if category == 'success' %}bg-green-100 text-green-700{% else %}bg-blue-100 text-blue-700{% endif %}">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

#### Server List (templates/index.html)

```html
{% extends "base.html" %}

{% block content %}
<h2 class="text-2xl font-bold mb-6">MCP Servers</h2>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    {% for server in servers %}
    <div class="bg-white rounded-lg shadow p-6">
        <h3 class="text-lg font-semibold mb-2">{{ server.name }}</h3>
        <p class="text-gray-600 text-sm mb-4">{{ server.description }}</p>
        
        <div class="flex items-center justify-between text-sm">
            <span class="px-2 py-1 bg-gray-100 rounded">{{ server.runtime_type }}</span>
            <div class="space-x-2">
                <button hx-post="/api/servers/{{ server.id }}/test"
                        hx-target="#test-{{ server.id }}"
                        class="text-blue-500 hover:text-blue-600">
                    Test
                </button>
                <a href="/servers/{{ server.id }}" class="text-blue-500 hover:text-blue-600">
                    View
                </a>
            </div>
        </div>
        <div id="test-{{ server.id }}" class="mt-2"></div>
    </div>
    {% endfor %}
</div>

{% if not servers %}
<div class="text-center py-12">
    <p class="text-gray-500 mb-4">No servers configured yet.</p>
    <a href="/servers/add" class="text-blue-500 hover:text-blue-600">Add your first server →</a>
</div>
{% endif %}
{% endblock %}
```

#### Add Server Form (templates/servers/add.html)

```html
{% extends "base.html" %}

{% block content %}
<div class="max-w-2xl mx-auto">
    <h2 class="text-2xl font-bold mb-6">Add MCP Server</h2>
    
    <form method="POST" class="space-y-6">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        
        <!-- GitHub URL Analysis -->
        <div class="bg-white p-6 rounded-lg shadow">
            <h3 class="text-lg font-medium mb-4">Step 1: Analyze Repository</h3>
            
            <div class="mb-4">
                <label class="block text-sm font-medium mb-2">GitHub URL</label>
                <input type="url" name="github_url" value="{{ github_url or '' }}"
                       class="w-full p-2 border rounded-md" 
                       placeholder="https://github.com/owner/repo" required>
            </div>
            
            <button type="submit" name="analyze" 
                    class="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
                Analyze with Claude
            </button>
        </div>
        
        {% if analysis %}
        <!-- Configuration Form -->
        <div class="bg-white p-6 rounded-lg shadow">
            <h3 class="text-lg font-medium mb-4">Step 2: Configure Server</h3>
            
            <div class="grid grid-cols-1 gap-4">
                <div>
                    <label class="block text-sm font-medium mb-2">Name</label>
                    <input type="text" name="name" value="{{ analysis.name }}"
                           class="w-full p-2 border rounded-md" required>
                </div>
                
                <div>
                    <label class="block text-sm font-medium mb-2">Description</label>
                    <input type="text" name="description" value="{{ analysis.description }}"
                           class="w-full p-2 border rounded-md">
                </div>
                
                <div>
                    <label class="block text-sm font-medium mb-2">Runtime</label>
                    <select name="runtime_type" class="w-full p-2 border rounded-md">
                        <option value="npx" {% if analysis.runtime_type == 'npx' %}selected{% endif %}>
                            Node.js (npx)
                        </option>
                        <option value="uvx" {% if analysis.runtime_type == 'uvx' %}selected{% endif %}>
                            Python (uvx)
                        </option>
                        <option value="docker" {% if analysis.runtime_type == 'docker' %}selected{% endif %}>
                            Docker
                        </option>
                    </select>
                </div>
                
                <div>
                    <label class="block text-sm font-medium mb-2">Install Command</label>
                    <input type="text" name="install_command" value="{{ analysis.install_command }}"
                           class="w-full p-2 border rounded-md">
                </div>
                
                <div>
                    <label class="block text-sm font-medium mb-2">Start Command</label>
                    <input type="text" name="start_command" value="{{ analysis.start_command }}"
                           class="w-full p-2 border rounded-md" required>
                </div>
            </div>
            
            <!-- Environment Variables -->
            {% if analysis.env_variables %}
            <div class="mt-6">
                <h4 class="text-md font-medium mb-3">Environment Variables</h4>
                {% for env in analysis.env_variables %}
                <div class="grid grid-cols-3 gap-2 mb-2">
                    <input type="text" name="env_keys[]" value="{{ env.key }}"
                           class="p-2 border rounded-md" placeholder="Key" readonly>
                    <input type="text" name="env_value_{{ env.key }}"
                           class="p-2 border rounded-md" placeholder="Value">
                    <input type="text" name="env_desc_{{ env.key }}" value="{{ env.description }}"
                           class="p-2 border rounded-md" placeholder="Description" readonly>
                </div>
                {% endfor %}
            </div>
            {% endif %}
            
            <div class="mt-6 flex justify-end space-x-3">
                <a href="/" class="px-4 py-2 border rounded-md hover:bg-gray-50">Cancel</a>
                <button type="submit" name="save"
                        class="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600">
                    Add Server
                </button>
            </div>
        </div>
        {% endif %}
    </form>
</div>
{% endblock %}
```

### Code Standards
- Clean, accurate, readable, and efficient code
- Comprehensive docstrings for all functions and classes
- Proper error handling and logging
- Type hints on all function parameters and return values
- Centralized API functionality rather than repeating across files
- Rate limiting and retries for all API requests
- Do not cut corners or leave updates for later. If you start code, finish it.

### Implementation Rules
- DO NOT add unnecessary complexity or features not requested
- DO NOT over-engineer solutions; prefer simplicity
- Authentication should be discovered from OpenAPI spec when possible
- Only GET and POST requests are supported for API endpoints
- Proper documentation for all public APIs
- Proper unittests (with unittest) for all major functionality


## Development Timeline

### Week 1: Foundation & Web UI
**Days 1-2: Project Setup**
- Initialize Flask project structure
- Set up SQLite database with SQLAlchemy
- Create basic models and forms
- Configure environment and dependencies

**Days 3-4: Web UI Implementation**
- Build Flask routes and views
- Create Jinja2 templates with TailwindCSS
- Implement server CRUD operations
- Add htmx for dynamic updates

**Day 5: Testing & Polish**
- Test server management flow
- Add error handling and validation
- Write basic unit tests

### Week 2: Container & MCP Integration
**Days 1-2: Container Management**
- Integrate llm-sandbox library
- Implement async bridge pattern
- Create container lifecycle manager
- Add resource limits and timeouts

**Days 3-4: FastMCP Integration**
- Set up FastMCP server
- Implement Python sandbox tool
- Create dynamic tool registration
- Test with local execution

**Day 5: Integration Testing**
- Test container spawning
- Verify tool execution
- Handle edge cases

### Week 3: Claude & Transport Support
**Days 1-2: Claude Analyzer**
- Integrate Anthropic SDK
- Implement GitHub file fetching
- Create analysis parser
- Test with various repositories

**Days 3-4: Transport Implementation**
- Add stdio transport support
- Implement HTTP transport
- Create transport adapters
- Test with different clients

**Day 5: Claude Desktop Integration**
- Generate configuration files
- Create setup instructions
- Test with Claude Desktop

### Week 4: Testing & Deployment
**Days 1-2: Comprehensive Testing**
- End-to-end workflow testing
- Load testing with multiple servers
- Security validation
- Bug fixes

**Days 3-4: Documentation**
- Write user guide
- Create API documentation
- Add inline code documentation
- Prepare deployment instructions

**Day 5: Final Polish**
- Performance optimization
- UI/UX improvements
- Final testing
- Deployment preparation

## Configuration Files

Project configuration is managed through modern Python packaging standards.

### Project Dependencies (`pyproject.toml`)
Dependencies are managed in `pyproject.toml`. The `requirements.txt` file can be generated from this for environments that need it, but `pyproject.toml` is the source of truth.

### Environment Variables (`.env.example`)
```bash
# Required for Flask sessions
SECRET_KEY=your-super-secret-key

# Required for repository analysis (Week 3)
ANTHROPIC_API_KEY=your-anthropic-api-key

# Optional, but recommended for higher GitHub API rate limits
GITHUB_TOKEN=your-github-token

# Optional: Overrides the default database location
# Default is 'data/mcp_router.db' in the project root
# DATABASE_URL=sqlite:///path/to/your/database.db

# Flask environment settings
FLASK_ENV=development
FLASK_DEBUG=True
```

### Docker Compose (`docker-compose.yml`)
Provides a simple way to run the application and its services locally.

```yaml
version: '3.8'

services:
  mcp-router:
    build: .
    ports:
      - "5001:5001"
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      # This ensures the database is created in the mapped volume
      - DATABASE_URL=sqlite:////app/data/mcp_router.db
    volumes:
      # Persist the database outside the container
      - ./data:/app/data
      # Mount source for hot-reloading in development
      - ./src:/app/src
    env_file:
      - .env
```

## Key Implementation Notes

1. **Async Bridge Pattern**: Use `asyncio.run_in_executor` to bridge llm-sandbox's sync API with FastMCP's async requirements

2. **Transport Focus**: Only implement stdio (for Claude Desktop) and HTTP (for remote). Skip deprecated SSE.

3. **Security**: Containers are isolated by default. Never expose host secrets to containers.

4. **Simplicity**: Single SQLite database, no authentication for MVP, minimal JavaScript.

5. **Error Handling**: Always return structured responses that LLMs can parse.

## Testing Checklist

- [ ] Can add MCP server via GitHub URL
- [ ] Claude analyzer extracts correct configuration
- [ ] Python sandbox executes code successfully
- [ ] Environment variables are properly managed
- [ ] Containers spawn and cleanup correctly
- [ ] Claude Desktop can connect via stdio
- [ ] Web UI updates dynamically with htmx
- [ ] Error states are handled gracefully

## Success Metrics

1. **Functional**: All 9 core requirements implemented
2. **Performance**: <3s container spawn time
3. **Reliability**: Graceful handling of failures
4. **Usability**: Non-technical users can add servers
5. **Security**: No host system exposure

This MVP provides a solid foundation that can be extended with authentication, monitoring, and advanced features in future iterations.