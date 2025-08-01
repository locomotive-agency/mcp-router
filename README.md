# MCP Router (Alpha)

🚀 **Load any tools from GitHub → Configure API keys → Select tools → Use anywhere**

A unified gateway for Model Context Protocol (MCP) servers that lets you discover, configure, and access tools from any GitHub repository through a single endpoint.

> ⚠️ **Alpha Software**: This project is in active development. APIs may change, and some features are experimental.

## What is MCP Router?

MCP Router simplifies using AI tools by:
- **Auto-discovering tools** from any GitHub repository
- **Managing API keys** and credentials in one place  
- **Selective tool access** - enable only what you need
- **Single endpoint** for all your tools (no more juggling configs)
- **Docker isolation** for secure tool execution

## Quick Start

### 🏃 Run Locally (2 minutes)

```bash
# Clone and setup
git clone https://github.com/locomotive-agency/mcp-router.git
cd mcp-router
pip install -r requirements.txt

# Configure (minimal setup)
cp env.example .env
# Edit .env - just add:
# ADMIN_PASSCODE=changeme123  (min 8 chars)
# ANTHROPIC_API_KEY=sk-ant-...  (for GitHub analysis)

# Run it!
python -m mcp_router
# Open http://localhost:8000
```

### 🚀 Deploy to Fly.io (5 minutes)

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Deploy
cd mcp-router
fly launch  # Follow prompts
fly secrets set ADMIN_PASSCODE=your-secure-password
fly secrets set ANTHROPIC_API_KEY=sk-ant-your-key
fly deploy

# Done! Access at https://your-app.fly.dev
```

## How It Works

### 1. Add Tools from GitHub

Navigate to the web UI and paste any MCP server GitHub URL:
- `https://github.com/modelcontextprotocol/servers` (official tools)
- `https://github.com/yzfly/mcp-python-interpreter` (Python sandbox)
- Any repository with MCP tools!

Claude automatically analyzes the repo and configures it for you.

### 2. Configure Your Tools

- **API Keys**: Store once, use everywhere
- **Toggle Tools**: Enable/disable specific tools
- **Docker Settings**: Automatic containerization for security

### 3. Connect Your Client

**For Claude Desktop:**
```json
{
  "mcpServers": {
    "mcp-router": {
      "command": "python",
      "args": ["-m", "mcp_router", "--transport", "stdio"]
    }
  }
}
```

**For Production (API):**
```python
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

async with Client(
    "https://your-app.fly.dev/mcp/",
    auth=BearerAuth(token="your-api-key")
) as client:
    tools = await client.list_tools()
```

## Key Features

### 🔧 Tool Discovery
- Automatic GitHub repository analysis
- Support for npx, uvx, and Docker-based tools
- Pre-configured with Python interpreter

### 🔒 Security
- Docker isolation for each tool
- OAuth 2.1 and API key authentication
- Selective tool enabling

### 🌐 Deployment Ready
- Single-command Fly.io deployment
- Built-in web UI for management
- Production-ready HTTP transport

## Architecture

```
Your App → MCP Router → Docker Containers → Individual Tools
            ↓
         Web UI (manage tools, keys, access)
```

## Contributing

We need help with:

### 1. 🔐 OAuth Authentication
- Current implementation in `src/mcp_router/mcp_oauth.py`
- Need: Production-ready token storage (Redis/DB)
- Need: Additional OAuth providers beyond basic flow
- Need: Refresh token implementation

### 2. ⚡ Starlette/Async Optimization
- Current ASGI app in `src/mcp_router/asgi.py`
- Need: Better async patterns for tool discovery
- Need: WebSocket support for real-time updates
- Need: Performance optimization for concurrent requests

### 3. 🐳 Docker Optimization
- Current implementation in `src/mcp_router/container_manager.py`
- Need: Container pooling for faster startup
- Need: Resource limits and monitoring
- Need: Multi-architecture image support

## Environment Variables

```bash
# Required
ADMIN_PASSCODE=changeme123       # Web UI password (min 8 chars)
ANTHROPIC_API_KEY=sk-ant-...     # For GitHub repo analysis

# Optional
MCP_AUTH_TYPE=api_key           # or "oauth" 
FLASK_PORT=8000                 # Web UI port
DOCKER_TIMEOUT=300              # Container operation timeout
```

## Development

```bash
# Run tests
pytest

# Run with debug logging
LOG_LEVEL=DEBUG python -m mcp_router

# Clear database for fresh start
python -m mcp_router --clear-db
```

## Support

- **Issues**: [GitHub Issues](https://github.com/locomotive-agency/mcp-router/issues)
- **Discussions**: [GitHub Discussions](https://github.com/locomotive-agency/mcp-router/discussions)

## License

See [LICENSE](LICENSE)

---

**Made with ❤️ by the MCP Router Team**

*Want to contribute? Check out our [contribution areas](#contributing) above!*