# MCP Router MVP Development Plan

## Executive Summary

MCP Router is a Python-based tool that acts as a unified gateway for multiple MCP (Model Context Protocol) servers. It provides a web UI for managing servers, analyzes GitHub repositories using Claude, and dynamically spawns containerized environments on-demand. The router uses FastMCP's proxy and middleware capabilities to present a hierarchical, intuitive interface to LLMs while maintaining compatibility with any MCP-compliant server regardless of implementation language.

**MVP Timeline:** 4 weeks, 1 developer  
**Core Stack:** Flask + htmx, FastMCP 2.x, llm-sandbox, SQLite  
**Transports:** stdio (local) and HTTP (remote) only

## Core MVP Features

1. **Web UI** - Flask with server-side rendering for server management
2. **Claude Analyzer** - Automated GitHub repository analysis
3. **Container Management** - Language-agnostic sandbox support (npx, uvx, docker)
4. **MCP Router with Smart Proxying** - Hierarchical tool discovery via FastMCP proxy + middleware
5. **Python Sandbox** - Built-in data science environment
6. **Transport Support** - stdio and HTTP only (skip deprecated SSE)
7. **Claude Desktop Integration** - Local configuration generator

## System Architecture

### High-Level Architecture

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
│  │  Web Server │  │  Proxy Router│     │
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
    │(Node.js)│ │(Python)│ │(Any)   │
    └────────┘ └───────┘ └────────┘
```

### MCP Router Design Pattern

The router uses FastMCP's composite proxy feature combined with custom middleware to provide an intuitive, hierarchical tool discovery interface:

```
LLM Experience:
1. tools/list → [python_sandbox, list_providers]
2. call: list_providers() → ["server1", "server2", ...]  (dynamically from DB)
3. tools/list(provider="server1") → [tool1, tool2, ...]
4. call: tool1(provider="server1", ...params)
```

This design prevents overwhelming LLMs with hundreds of tools while maintaining a stateless, scalable architecture.

## Technology Stack

### Backend
- **Python 3.11+** - Core language
- **Flask 2.3+** - Web framework
- **FastMCP 2.9+** - MCP protocol implementation with proxy and middleware support
- **llm-sandbox** - Container runtime management (supports any language)
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
│       ├── claude_analyzer.py
│       ├── config.py
│       ├── container_manager.py
│       ├── forms.py
│       ├── middleware.py      # Custom MCP middleware
│       ├── models.py
│       ├── server.py
│       ├── static/            # For CSS, JS, images
│       └── templates/
│           ├── *.html
│           └── servers/*.html
└── tests/
    ├── __init__.py
    └── test_*.py
```

## Core Implementation

### 1. FastMCP Router with Proxy and Middleware (server.py)

```python
import asyncio
import logging
from fastmcp import FastMCP
from mcp_router.middleware import ProviderFilterMiddleware
from mcp_router.container_manager import ContainerManager
from mcp_router.models import get_active_servers
from mcp_router.app import app

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def create_mcp_config(servers):
    """Convert database servers to MCP config format for proxy"""
    config = {"mcpServers": {}}
    
    for server in servers:
        # Each server becomes a proxy target
        config["mcpServers"][server.name] = {
            "command": server.start_command,
            "args": server.start_command.split()[1:] if len(server.start_command.split()) > 1 else [],
            "env": {env["key"]: env["value"] for env in server.env_variables if env.get("value")},
            "transport": "stdio"  # Sandboxed servers use stdio
        }
    
    return config

def main():
    """Main function to run the MCP server."""
    log.info("Starting MCP Router server...")
    
    # Fetch active servers from database
    with app.app_context():
        active_servers = get_active_servers()
    
    # Create proxy configuration
    config = create_mcp_config(active_servers)
    
    # Create the router as a composite proxy
    router = FastMCP.as_proxy(
        config,
        name="MCP-Router",
        instructions="""This router provides access to multiple MCP servers and a Python sandbox.
        Use 'list_providers' to see available servers, then use tools/list with a provider parameter."""
    )
    
    # Add the Python sandbox tool directly to router
    @router.tool()
    def python_sandbox(code: str, libraries: list[str] = None) -> dict:
        """Execute Python code in a secure sandbox with data science libraries."""
        # Implementation remains the same
        ...
    
    @router.tool()
    def list_providers() -> list[str]:
        """List all available MCP server providers"""
        return [server.name for server in active_servers]
    
    # Add middleware for hierarchical discovery
    router.add_middleware(ProviderFilterMiddleware())
    
    # Run with stdio for Claude Desktop
    log.info("Running with stdio transport for Claude Desktop.")
    router.run(transport="stdio")

if __name__ == "__main__":
    main()
```

### 2. Provider Filter Middleware (middleware.py)

```python
from fastmcp.server.middleware import Middleware, MiddlewareContext
import logging

log = logging.getLogger(__name__)

class ProviderFilterMiddleware(Middleware):
    """
    Middleware that implements hierarchical tool discovery.
    
    - Without provider param: shows only discovery tools
    - With provider param: shows only that provider's tools
    """
    
    async def on_tools_list(self, ctx: MiddlewareContext, call_next):
        """Filter tool listings based on provider parameter"""
        provider = ctx.params.get("provider") if ctx.params else None
        
        # Get the full tool list
        result = await call_next(ctx)
        
        if provider:
            # Filter to show only tools from the specified provider
            filtered_tools = []
            for tool in result.get("tools", []):
                if tool["name"].startswith(f"{provider}_"):
                    # Remove the prefix for cleaner presentation
                    tool_copy = tool.copy()
                    tool_copy["name"] = tool["name"][len(provider)+1:]
                    filtered_tools.append(tool_copy)
            result["tools"] = filtered_tools
            log.info(f"Filtered tools for provider '{provider}': {len(filtered_tools)} tools")
        else:
            # Show only discovery tools when no provider specified
            discovery_tools = ["python_sandbox", "list_providers"]
            result["tools"] = [
                t for t in result.get("tools", []) 
                if t["name"] in discovery_tools
            ]
            log.info("Showing discovery tools only")
        
        return result
    
    async def on_tool_call(self, ctx: MiddlewareContext, call_next):
        """Add provider prefix to tool calls when provider is specified"""
        # Extract provider from tool arguments if present
        if ctx.params and "arguments" in ctx.params:
            args = ctx.params["arguments"]
            provider = args.pop("provider", None)
            
            if provider and "_" not in ctx.params.get("name", ""):
                # Add provider prefix to the tool name
                original_name = ctx.params["name"]
                ctx.params["name"] = f"{provider}_{original_name}"
                log.info(f"Rewriting tool call: {original_name} -> {ctx.params['name']}")
        
        return await call_next(ctx)
```

### 3. Container Manager (container_manager.py)

The container manager provides optimized container lifecycle management with lightweight images:

```python
"""
Manages container lifecycle for MCP servers in any language.

Supports:
- npx: Node.js/JavaScript servers (using Alpine images)
- uvx: Python servers (using Alpine or slim images)
- docker: Any language via Docker images
"""
import asyncio
import logging
import os
from typing import Dict, Any, Optional
from llm_sandbox import SandboxSession
from mcp_router.models import get_server_by_id, MCPServer

logger = logging.getLogger(__name__)

class ContainerManager:
    """Manages container lifecycle with language-agnostic sandbox support"""
    
    def _create_sandbox_session(self, server: MCPServer) -> SandboxSession:
        """
        Create a sandbox session based on server runtime type.
        
        Uses lightweight Alpine images by default for faster container spawning:
        - Node.js: node:20-alpine (~50MB vs ~400MB for full)
        - Python: python:3.11-alpine (~50MB vs ~150MB for slim)
        
        For Python servers requiring compiled dependencies (numpy, pandas, etc.),
        set MCP_PYTHON_IMAGE=python:3.11-slim-bullseye
        """
        env_vars = self._get_env_vars(server)
        docker_host = "unix:///Users/jroakes/.docker/run/docker.sock"
        
        if server.runtime_type == "npx":
            # Node.js/JavaScript servers with Alpine
            return SandboxSession(
                lang="javascript",
                runtime="node",
                image="node:20-alpine",
                timeout=30,
                env_vars=env_vars,
                docker_host=docker_host,
                keep_env=True,  # Reuse containers for performance
            )
        elif server.runtime_type == "uvx":
            # Python servers with configurable image
            python_image = os.environ.get('MCP_PYTHON_IMAGE', 'python:3.11-alpine')
            return SandboxSession(
                lang="python",
                image=python_image,
                timeout=30,
                env_vars=env_vars,
                docker_host=docker_host,
                keep_env=True,  # Reuse containers for performance
            )
        elif server.runtime_type == "docker":
            # Any language via Docker
            return SandboxSession(
                image=server.start_command,
                timeout=30,
                env_vars=env_vars,
                docker_host=docker_host,
                keep_env=True,  # Reuse containers for performance
            )
        else:
            raise ValueError(f"Unsupported runtime type: {server.runtime_type}")
    
    def pull_server_image(self, server_id: str) -> Dict[str, Any]:
        """
        Pull Docker image for a specific server.
        Called automatically when a server is added via the web UI.
        """
        # Implementation pulls the appropriate lightweight image
        ...
```

### 4. Database Models (models.py)

Models remain unchanged - servers are stored with their runtime configuration and loaded dynamically.

### 5. Flask Web Application (app.py)

The web application has been enhanced with automatic Docker image pulling:
- When a server is added, its Docker image is automatically pulled in the background
- This ensures fast first-time execution without blocking the UI
- Uses lightweight Alpine images by default for faster downloads

### 6. Claude Repository Analyzer (claude_analyzer.py)

The analyzer remains unchanged, automatically detecting:
- Runtime type (npx, uvx, docker)
- Installation commands
- Start commands
- Required environment variables

## Performance Optimizations

### Container Spawning Performance

The system implements several optimizations to minimize container startup latency:

1. **Lightweight Alpine Images**
   - Node.js: `node:20-alpine` (~50MB vs ~400MB for full image)
   - Python: `python:3.11-alpine` (~50MB vs ~150MB for slim image)
   - Results in 5-10x faster image downloads

2. **Image Pre-pulling on Server Addition**
   - Docker images are automatically pulled when a server is added
   - First test/execution is fast since image is already cached
   - No bulk pre-pulling on startup - images pulled only when needed

3. **Container Reuse**
   - `keep_env=True` ensures containers are reused between runs
   - Subsequent operations are significantly faster (<2s vs 30-60s)

4. **Configurable Python Images**
   - Set `MCP_PYTHON_IMAGE` for compatibility with compiled dependencies
   - Example: `MCP_PYTHON_IMAGE=python:3.11-slim-bullseye` for numpy/pandas

### Expected Performance

- **Image pull time**: 5-15s with Alpine images (vs 30-60s with standard images)
- **First test after adding server**: <5s (image pre-pulled)
- **Subsequent tests**: <2s (container reused)
- **Web server startup**: No delay (no bulk pre-pulling)

## Key Implementation Notes

1. **Dynamic Server Loading**: No servers are hardcoded. All servers come from the database and can be added/removed via the web UI.

2. **Language Agnostic**: The sandbox system supports any programming language:
   - JavaScript/TypeScript via npx
   - Python via uvx
   - Any language via Docker containers

3. **Hierarchical Discovery**: The middleware pattern prevents tool overload by implementing a two-step discovery process.

4. **Stateless Design**: No session state is maintained. The provider context is passed in each request.

5. **Security**: Each server runs in an isolated sandbox container with no access to the host system.

6. **Performance**: Optimized for fast container spawning with lightweight images and smart caching.

## Testing Checklist

- [ ] Can add MCP server via GitHub URL (any language)
- [ ] Claude analyzer extracts correct configuration
- [ ] Docker image pulls automatically on server addition
- [ ] Python sandbox executes code successfully
- [ ] list_providers shows all active servers from DB
- [ ] tools/list with provider param shows filtered tools
- [ ] Tool calls with provider param route correctly
- [ ] Environment variables are properly managed
- [ ] Containers spawn quickly (<5s first run, <2s subsequent)
- [ ] Claude Desktop can connect via stdio
- [ ] Web UI updates dynamically with htmx

## Success Metrics

1. **Functional**: All core requirements implemented
2. **Performance**: <5s first container spawn, <2s subsequent spawns
3. **Reliability**: Graceful handling of failures
4. **Usability**: Intuitive hierarchical discovery
5. **Flexibility**: Support for any MCP server regardless of language
6. **Security**: Complete sandbox isolation
7. **Efficiency**: Minimal resource usage with Alpine images

This MVP provides a solid foundation that can be extended with authentication, monitoring, and advanced features in future iterations.