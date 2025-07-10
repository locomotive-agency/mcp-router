# MCP Router

A unified gateway for Model Context Protocol (MCP) servers with dual transport support, web management, intelligent routing, and sandboxed execution.

![MCP Router Demo](assets/intro.gif)

## What It Does

MCP Router provides:
- **Dual Transport Architecture**: Both HTTP (remote/production) and STDIO (local development) modes from a single application
- **Single Gateway**: Unified access to multiple MCP servers (no more juggling configs)
- **Web UI**: Server management with real-time status and configuration
- **Smart Routing**: Hierarchical tool discovery (prevents LLM tool overload)
- **Sandboxed Execution**: Docker-based Python sandbox and containerized MCP servers
- **Production Ready**: OAuth 2.1 and API key authentication for remote access

## Quick Deploy to Fly.io

```bash
# Install Fly CLI if you haven't already
brew install flyctl  # or see https://fly.io/docs/getting-started/

# Clone and deploy
git clone https://github.com/locomotive-agency/mcp-router.git
cd mcp-router
fly launch  # Follow prompts to create app
fly deploy

# Access your deployment
# Web UI: https://your-app-name.fly.dev
# MCP endpoint: https://your-app-name.fly.dev/mcp/
```

## Local Development

```bash
# Clone repository
git clone https://github.com/locomotive-agency/mcp-router.git
cd mcp-router

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp env.example .env
nano .env  # Add ANTHROPIC_API_KEY and ADMIN_PASSCODE

# HTTP Mode (Production-like, single port)
python -m mcp_router --transport http
# Access web UI: http://localhost:8000
# MCP endpoint: http://localhost:8000/mcp/

# STDIO Mode (Local development, background web UI)
python -m mcp_router --transport stdio
# Access web UI: http://localhost:8000 (background)
# Connect via Claude Desktop (stdio)
```

## Configuration

### Essential Environment Variables

```bash
# Required
ADMIN_PASSCODE=your-secure-passcode    # Web UI authentication
ANTHROPIC_API_KEY=sk-ant-...          # For GitHub repo analysis

# Transport Mode (can be overridden with --transport flag)
MCP_TRANSPORT=http                     # "stdio" or "http" (default: http)

# Authentication (HTTP Mode)
MCP_API_KEY=auto-generated             # API key for HTTP mode authentication
MCP_OAUTH_ENABLED=true                 # Enable OAuth 2.1 support

# OAuth Settings (when enabled)
OAUTH_ISSUER=""                        # JWT issuer (auto-detected if blank)
OAUTH_AUDIENCE=mcp-server              # OAuth audience identifier
OAUTH_TOKEN_EXPIRY=3600                # Token lifetime in seconds

# Server Configuration
FLASK_PORT=8000                        # Application port
MCP_PATH=/mcp                          # MCP endpoint path (HTTP mode)
```

### Fly.io Deployment

Your `fly.toml` configures:
- Single service on port 8000 serving both Web UI and MCP endpoints
- HTTPS termination at the edge
- Persistent volume at `/data` for SQLite database
- Automatic HTTP mode startup via `python -m mcp_router`

## Usage

### 1. Add MCP Servers

Via Web UI:
1. Navigate to "Add Server"
2. Paste GitHub repository URL
3. Claude analyzes and configures automatically
4. Review and save

### 2. Connect Your Client

**STDIO Mode (Local Development):**

First, start MCP Router in STDIO mode:
```bash
python -m mcp_router --transport stdio
# Web UI available at http://localhost:8000 for management
```

Then configure Claude Desktop:
```json
{
  "mcpServers": {
    "mcp-router-local": {
      "command": "python",
      "args": ["-m", "mcp_router", "--transport", "stdio"]
    }
  }
}
```

**HTTP Mode (Remote/Production):**
```python
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

# For deployed instance with API key
async with Client(
    "https://your-app.fly.dev/mcp/",
    auth=BearerAuth(token="your-api-key")
) as client:
    # List available servers
    providers = await client.call_tool("list_providers")
    
    # Use hierarchical tool discovery
    result = await client.call_tool(
        "search_code",
        provider="github-mcp-server",
        query="authentication"
    )
```

### 3. OAuth Support

For OAuth-enabled providers:
1. Configure OAuth credentials in server settings
2. Users authenticate via standard OAuth flow
3. Tokens managed automatically per session

## Architecture

### Dual Transport Design

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Router Core Logic                        │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────────────┐  │
│  │ SQLite DB   │ │ Router       │ │ Container Manager        │  │
│  │ (Servers)   │ │ Factory      │ │ (Docker)                 │  │
│  └─────────────┘ └──────────────┘ └──────────────────────────┘  │
└──────────────────────┬──────────────────────┬───────────────────┘
                       │                      │
        ┌──────────────▼──────────────┐      ┌▼──────────────────────┐
        │    HTTP Mode (Production)   │      │ STDIO Mode (Local Dev)│
        │                             │      │                       │
        │ ┌─────────────────────────┐ │      │ ┌───────────────────┐ │
        │ │ Starlette ASGI:         │ │      │ │ FastMCP stdio     │ │
        │ │ - Flask UI at /         │ │      │ │ (Main Thread)     │ │
        │ │ - FastMCP at /mcp       │ │      │ └───────────────────┘ │
        │ │ - Single Port 8000      │ │      │ ┌───────────────────┐ │
        │ └─────────────────────────┘ │      │ │ Flask UI          │ │
        │                             │      │ │ (Background)      │ │
        └─────────────┬───────────────┘      └───────┬───────────────┘
                      │                              │
        ┌─────────────▼───────────────┐    ┌─────────▼─────────────┐
        │   Web Browser/Claude Web    │    │    Claude Desktop     │
        │   (OAuth/API Key Auth)      │    │    (No Auth)          │
        └─────────────────────────────┘    └───────────────────────┘
```

### Hierarchical Tool Discovery

1. **Initial**: Only `list_providers` and `python_sandbox` visible
2. **Discovery**: `list_providers()` returns available servers
3. **Server Tools**: Access via `provider` parameter
4. **Execution**: Routed to appropriate sandboxed container

## Development

### Running Tests
```bash
pytest -v
```

### Key Components
- `src/mcp_router/server.py` - FastMCP server implementation
- `src/mcp_router/web.py` - Flask web interface
- `src/mcp_router/container_manager.py` - Docker orchestration
- `src/mcp_router/mcp_oauth.py` - OAuth provider support

## Troubleshooting

**Port conflicts:**
```bash
# Change in .env
FLASK_PORT=8080
MCP_PORT=8002
```

**Docker issues:**
```bash
# Verify Docker running
docker ps

# Clear containers
docker system prune -a
```

**Authentication failures:**
- Ensure `ADMIN_PASSCODE` is set (min 8 chars)
- Check API key in MCP Control panel
- Verify OAuth credentials if using OAuth

## Contributing

Focus areas:
1. Additional OAuth provider support
2. Performance optimizations
3. Enhanced security features


## License
See LICENSE