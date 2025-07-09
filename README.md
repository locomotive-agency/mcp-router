# MCP Router

A unified gateway for Model Context Protocol (MCP) servers with web management, intelligent routing, and sandboxed execution.

![MCP Router Demo](assets/intro.gif)

## Ahrefs Key
YkMTiZt0k5Yy0GVKthqV4aW5jhtxNvdkWOEmHmT6

## What It Does

MCP Router provides:
- **Single gateway** for multiple MCP servers (no more juggling configs)
- **Web UI** for server management with real-time control
- **Smart routing** with hierarchical tool discovery (prevents LLM overload)
- **Sandboxed execution** via Docker for any language
- **Remote access** with HTTP transport and OAuth/API key authentication

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

# Quick setup (assumes Docker installed)
chmod +x setup-deploy.sh
./setup-deploy.sh

# Configure environment
cp env.example .env
nano .env  # Add ANTHROPIC_API_KEY and ADMIN_PASSCODE

# Run locally
python -m mcp_router.web

# Access at http://localhost:8000
```

## Configuration

### Essential Environment Variables

```bash
# Required
ADMIN_PASSCODE=your-secure-passcode    # Web UI authentication
ANTHROPIC_API_KEY=sk-ant-...          # For GitHub repo analysis

# Transport (configured via UI)
MCP_TRANSPORT=http                     # stdio or http
MCP_API_KEY=auto-generated             # For HTTP auth
MCP_OAUTH_ENABLED=true                 # Enable OAuth support
```

### Fly.io Specific

Your `fly.toml` configures:
- Web UI on port 443 (HTTPS)
- MCP server on port 8001
- Persistent volume at `/data` for SQLite
- Auto-generated environment variables

## Usage

### 1. Add MCP Servers

Via Web UI:
1. Navigate to "Add Server"
2. Paste GitHub repository URL
3. Claude analyzes and configures automatically
4. Review and save

### 2. Connect Your Client

**Claude Desktop (stdio mode):**
```json
{
  "mcpServers": {
    "mcp-router": {
      "command": "python",
      "args": ["-m", "mcp_router.server"]
    }
  }
}
```

**Remote Access (HTTP mode):**
```python
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

# For deployed instance
async with Client(
    "https://your-app.fly.dev/mcp/",
    auth=BearerAuth(token="your-api-key")
) as client:
    # List available servers
    providers = await client.call_tool("list_providers")
    
    # Use a specific server's tools
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

```
┌─────────────┐     ┌─────────────┐
│   Claude    │     │  Your App   │
│  (stdio)    │     │   (HTTP)    │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └────────┬──────────┘
                │
         MCP Router
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼────┐  ┌───▼────┐ ┌────▼────┐
│  NPX   │  │  UVX   │ │ Docker  │
│Servers │  │Servers │ │ Custom  │
└────────┘  └────────┘ └─────────┘
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