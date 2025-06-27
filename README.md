# MCP Router

![MCP Router Demo](assets/intro.gif)

MCP Router is a Python-based unified gateway for multiple Model Context Protocol (MCP) servers. It provides a web interface for managing servers, intelligent routing with hierarchical tool discovery, and sandboxed execution environments for any programming language.

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/mcp-router.git
cd mcp-router

# Run the setup script (installs Docker and sets up the project)
chmod +x setup.sh
./setup.sh

# Edit configuration
nano .env  # Add your ANTHROPIC_API_KEY and set ADMIN_PASSCODE

# Start the web interface
source venv/bin/activate
python -m mcp_router.web

# Open in browser
open http://localhost:8000
```

## 🎯 Key Features

### Core Functionality
- **Unified MCP Gateway**: Single interface for multiple MCP servers
- **Web Management UI**: Flask-based interface with real-time updates via htmx
- **Intelligent Routing**: Hierarchical tool discovery prevents tool overload
- **Language Agnostic**: Support for any programming language via sandboxed containers
- **Built-in Python Sandbox**: Data science environment with popular libraries
- **Authentication**: Passcode-protected admin interface for secure remote hosting

### Server Management
- **GitHub Integration**: Automatic MCP server detection and configuration from repos
- **Claude Analysis**: AI-powered extraction of server requirements
- **Container Sandboxing**: Secure isolation using Docker (npx, uvx, or custom images)
- **Real-time Control**: Start/stop servers with live log streaming
- **Persistent Storage**: SQLite database for configurations

### Transport & Integration
- **Multiple Transports**: stdio (local) and HTTP (remote) with authentication
- **Claude Desktop Ready**: Direct integration with Anthropic's desktop app
- **API Authentication**: Secure access with API keys for remote connections
- **Auto-discovery**: Dynamic server and tool discovery without restarts

## 📋 Prerequisites

- **Python 3.11+** - Core runtime
- **Docker** - Required for sandboxed execution
- **Git** - For cloning repositories
- **Anthropic API Key** - For Claude repository analysis (optional but recommended)

## 🛠️ Installation

### Option 1: Automated Setup (Recommended)

We provide a setup script that handles Docker installation and project setup:

```bash
chmod +x setup.sh
./setup.sh
```

The script will:
- Install Docker (Ubuntu/Debian, Fedora, macOS)
- Verify Python 3.11+ is installed
- Create a virtual environment
- Install project dependencies
- Set up configuration files
- Create necessary directories

### Option 2: Manual Setup

1. **Install Docker**
   - Ubuntu/Debian: Follow [Docker's official guide](https://docs.docker.com/engine/install/ubuntu/)
   - macOS: Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - Other: See [Docker installation docs](https://docs.docker.com/get-docker/)

2. **Clone and Install**
   ```bash
   git clone https://github.com/yourusername/mcp-router.git
   cd mcp-router
   
   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install package
   pip install -e .
   
   # Create data directory
   mkdir -p data
   
   # Copy environment template
   cp env.example .env
   ```

3. **Configure Environment**
   Edit `.env` file with your settings:
   ```bash
   # Required for security
   ADMIN_PASSCODE=your-secure-passcode-here
   
   # Required for repository analysis
   ANTHROPIC_API_KEY=your-api-key-here
   
   # Optional customizations
   MCP_PYTHON_IMAGE=python:3.11-slim
   MCP_NODE_IMAGE=node:20-slim
   ```

## 🔐 Authentication

MCP Router includes a simple passcode-based authentication system to protect the admin interface when hosted remotely.

### Setting Up Authentication

1. **Set a strong passcode** in your `.env` file:
   ```bash
   ADMIN_PASSCODE=your-secure-passcode-here
   ```
   - Minimum 8 characters required
   - Use a strong, unique passcode
   - **Never use the default passcode in production!**

2. **First-time login**:
   - Navigate to http://localhost:8000
   - You'll be redirected to the login page
   - Enter your passcode
   - You'll stay logged in until you explicitly log out

3. **Security Notes**:
   - The passcode is hashed using bcrypt
   - Sessions persist across browser restarts
   - Always use HTTPS in production
   - Consider additional security measures (VPN, IP restrictions) for sensitive deployments

## 🚦 Usage

### Starting the Application

1. **Start Web Interface**
   ```bash
   source venv/bin/activate
   python -m mcp_router.web
   ```
   Access at: http://localhost:8000
   
   **First time**: You'll be prompted to log in with your passcode.

2. **Add MCP Servers**
   - Click "Add Server" in the web UI
   - Enter a GitHub repository URL
   - Claude will analyze and configure automatically
   - Review and save the configuration

3. **Control MCP Server**
   - Navigate to "MCP Control" in the navigation bar
   - Select transport mode (stdio for Claude Desktop, HTTP for remote)
   - Click "Start Server" to launch
   - Copy connection details for your client

### Integration Examples

#### Claude Desktop Integration
1. Start MCP server in stdio mode via Control Panel
2. Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "mcp-router": {
         "command": "/path/to/venv/bin/python",
         "args": ["-m", "mcp_router.server"]
       }
     }
   }
   ```
3. Restart Claude Desktop

#### Remote HTTP Access
```python
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

# Connect to HTTP transport
async with Client(
    "http://localhost:8001/mcp/",
    auth=BearerAuth(token="your-api-key")
) as client:
    # List available providers
    providers = await client.call_tool("list_providers")
    print(f"Available servers: {providers}")
    
    # List tools from a specific provider
    tools = await client.list_tools(provider="github-mcp-server")
    
    # Call a tool
    result = await client.call_tool(
        "search_repositories",
        provider="github-mcp-server",
        query="mcp servers"
    )
```

### Docker Compose Deployment
```bash
docker-compose up --build
```
- Web UI: http://localhost:8000
- MCP Server: http://localhost:8001/mcp/

## 🏗️ Architecture

### System Design
```
┌─────────────────┐     ┌─────────────────┐
│  Claude Desktop │     │   Web Browser   │
│   (stdio)       │     │   (Admin UI)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │ stdio                 │ HTTP
         │                       │
┌────────┴───────────────────────┴────────┐
│           MCP Router Service            │
│  ┌─────────────┐  ┌──────────────┐     │
│  │ Flask Web   │  │ FastMCP      │     │
│  │ Interface   │  │ Proxy Router │     │
│  └─────────────┘  └──────────────┘     │
│  ┌─────────────┐  ┌──────────────┐     │
│  │   Claude    │  │  Container   │     │
│  │  Analyzer   │  │  Manager     │     │
│  └─────────────┘  └──────────────┘     │
└─────────────────────────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
┌───▼────┐    ┌────▼────┐    ┌────▼────┐
│  NPX   │    │   UVX   │    │ Docker  │
│(Node.js)│    │(Python) │    │  (Any)  │
└────────┘    └─────────┘    └─────────┘
```

### Hierarchical Tool Discovery

The router implements a two-step discovery pattern to prevent overwhelming LLMs:

1. **Initial Tools**: Only `python_sandbox` and `list_providers` visible
2. **Provider Discovery**: `list_providers()` returns available servers
3. **Server Tools**: `tools/list(provider="server_name")` shows server-specific tools
4. **Tool Execution**: Tools called with `provider` parameter for routing

This design maintains a clean, stateless architecture while providing intuitive navigation.

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with:

```bash
# Flask Configuration
FLASK_PORT=8000
FLASK_ENV=development
SECRET_KEY=your-secret-key-here

# Authentication (REQUIRED for security)
ADMIN_PASSCODE=your-secure-passcode-here

# Claude API (Required for GitHub analysis)
ANTHROPIC_API_KEY=sk-ant-...

# Docker Configuration
DOCKER_HOST=unix:///var/run/docker.sock  # Linux/Mac
# DOCKER_HOST=tcp://localhost:2375       # Windows

# Container Images (Optional)
MCP_PYTHON_IMAGE=python:3.11-slim  # For Python servers
MCP_NODE_IMAGE=node:20-slim        # For Node.js servers

# MCP Server Configuration (Set via UI)
MCP_TRANSPORT=http      # stdio, http, or sse
MCP_HOST=127.0.0.1
MCP_PORT=8001
MCP_PATH=/mcp
MCP_API_KEY=auto-generated-if-not-set
```

### Supported Runtimes

| Runtime | Command | Use Case | Base Image |
|---------|---------|----------|------------|
| npx | `npx @org/package` | Node.js/TypeScript servers | `node:20-slim` |
| uvx | `uvx package` | Python servers | `python:3.11-slim` |
| docker | `docker run ...` | Any language/custom setup | User specified |

## 🧪 Development

### Running Tests
```bash
source venv/bin/activate
pytest -v
```

### Test Coverage
- ✅ Claude repository analyzer
- ✅ Middleware provider filtering  
- ✅ Database models and operations
- ✅ Log level detection
- ✅ Web UI routes and functionality
- ✅ Authentication system

### Project Structure
```
mcp-router/
├── src/mcp_router/      # Main package
│   ├── app.py          # Flask application
│   ├── auth.py         # Authentication system
│   ├── server.py       # MCP server with FastMCP
│   ├── container_manager.py  # Docker container lifecycle
│   ├── claude_analyzer.py    # GitHub repo analysis
│   ├── middleware.py   # Provider filter middleware
│   ├── models.py       # SQLAlchemy models
│   ├── server_manager.py     # MCP server processes
│   ├── templates/      # Jinja2 templates
│   └── static/         # CSS, JS assets
├── tests/              # Test suite
├── data/               # SQLite database
├── docker-compose.yml  # Container orchestration
├── setup.sh           # Automated setup script
└── .env.example       # Environment template
```

## 🚀 Performance

### Optimization Strategies

1. **Smart Image Management**
   - Common base images pre-pulled on startup
   - Shared layers between containers
   - Configurable slim images for minimal size

2. **Container Lifecycle**
   - Containers reused between operations
   - First run: ~5 seconds (after image pull)
   - Subsequent runs: <2 seconds

3. **Efficient Routing**
   - Stateless design with no session overhead
   - Direct stdio communication for local clients
   - Minimal middleware processing

## 🐛 Troubleshooting

### Common Issues

**Docker not running**
```bash
# Linux
sudo systemctl start docker

# macOS
# Start Docker Desktop from Applications
```

**Permission denied errors**
```bash
# Add user to docker group (Linux)
sudo usermod -aG docker $USER
# Log out and back in
```

**NPM idealTree errors**
- The system automatically cleans npm cache
- If persists, manually clear: `docker system prune`

**Port already in use**
```bash
# Change port in .env file
FLASK_PORT=8080
MCP_PORT=8002
```

**Login issues**
- Ensure ADMIN_PASSCODE is set in .env
- Minimum 8 characters required
- Clear browser cookies if having persistent issues

## 📚 Additional Resources

- [Model Context Protocol Specification](https://modelcontextprotocol.io)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Project Planning Document](project.md)
- [Docker Documentation](https://docs.docker.com)

## 🤝 Contributing

This is an MVP project with a focused 4-week timeline. Contributions should align with the roadmap in `project.md`.

### Development Priorities
1. Core functionality and stability
2. Test coverage and documentation
3. Performance optimizations
4. Additional transport implementations

## 📄 License

[License information to be added]

## 🙏 Acknowledgments

- Built with [FastMCP](https://github.com/jlowin/fastmcp) for MCP protocol implementation
- UI powered by [htmx](https://htmx.org) for seamless interactions
- Container sandboxing via [llm-sandbox](https://github.com/coleam00/llm-sandbox) 