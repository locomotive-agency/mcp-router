# MCP Router

MCP Router is a Python-based tool that acts as a unified gateway for multiple MCP (Model Context Protocol) servers. This project is structured as an installable Python package for easy development and deployment.

## Features

- **Web UI**: Flask-based interface for server management
- **Server CRUD**: Add, edit, delete, and toggle MCP servers
- **MCP Server Control**: Start/stop MCP server with different transports from web UI
- **Persistent Storage**: SQLite database for server configurations
- **Claude Repository Analyzer**: Automatic MCP server detection from GitHub repos
- **Container Management**: Language-agnostic sandbox support (npx, uvx, docker)
- **Smart Proxying**: Hierarchical tool discovery via FastMCP proxy + middleware
- **Python Sandbox**: Built-in data science environment
- **Multiple Transports**: stdio (local) and HTTP (remote) support
- **Authentication**: API key authentication for secure HTTP access
- **Claude Desktop Integration**: Local configuration generator

## Project Structure

```
mcp-router/
├── .gitignore
├── env.example              # Example environment configuration
├── data/                    # SQLite database storage
│   └── .gitignore
├── docker-compose.yml
├── Dockerfile
├── project.md              # Detailed project documentation
├── pyproject.toml
├── README.md
├── requirements.txt
├── src/
│   └── mcp_router/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py          # Flask web application
│       ├── claude_analyzer.py
│       ├── config.py
│       ├── container_manager.py
│       ├── forms.py
│       ├── middleware.py   # MCP middleware
│       ├── models.py
│       ├── server.py       # MCP server implementation
│       ├── static/
│       ├── templates/
│       └── web.py
└── tests/
    └── ... (test modules)
```

## Installation & Setup

### Prerequisites

- Python 3.11+
- Docker (for container management)
- A modern Python package manager like `pip` or `uv`

### 1. Clone the Repository

```bash
git clone <repository-url>
cd mcp-router
```

### 2. Create Environment

Create a virtual environment to isolate dependencies.

**Using `venv`:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Using `uv`:**
```bash
uv venv
source .venv/bin/activate
```

### 3. Install Dependencies

Install the project in editable mode:

**Using `pip`:**
```bash
pip install -e .
```

**Using `uv`:**
```bash
uv pip install -e .
```

### 4. Configure Environment Variables

Copy the example environment file and configure:

```bash
cp env.example .env
# Edit .env with your configuration
```

Key configuration options:
- `FLASK_SECRET_KEY`: Required for Flask sessions
- `ANTHROPIC_API_KEY`: For Claude repository analyzer
- `MCP_TRANSPORT`: Choose `stdio` (default) or `http`
- `MCP_API_KEY`: Required for secure HTTP transport
- `DOCKER_HOST`: Docker socket location (platform-specific)
- `MCP_PYTHON_IMAGE`: Python image for uvx servers (default: python:3.11-slim)
- `MCP_NODE_IMAGE`: Node.js image for npx servers (default: node:20-slim)

## Running the Application

### 1. Web UI (Server Management)

Start the Flask web interface:

```bash
python -m mcp_router.web
# or
mcp-router-web
```

The web interface will be available at `http://localhost:8000`.

### 2. MCP Server (stdio transport - Claude Desktop)

For local Claude Desktop integration:

```bash
python -m mcp_router
# or
mcp-router
```

### 3. MCP Server (HTTP transport - Remote Access)

For remote access via HTTP, use the MCP Control panel in the web UI:

1. Navigate to http://localhost:8000/mcp-control
2. Select "HTTP" transport
3. Configure host, port, and path
4. Click "Start Server"

Or via command line:

```bash
# Set environment variables
export MCP_TRANSPORT=http
export MCP_API_KEY=your-secure-api-key

# Run the server
python -m mcp_router
```

The HTTP endpoint will be available at `http://127.0.0.1:8001/mcp`.

### 4. Docker Compose

Run both web UI and MCP server:

```bash
docker-compose up --build
```

## Transport Modes

### stdio Transport (Default)
- Used for local integrations like Claude Desktop
- Each client spawns its own server process
- Communication via standard input/output

### HTTP Transport
- Enables remote MCP access
- Single persistent server instance
- Supports authentication via API keys
- Ideal for cloud deployments and Claude.ai integration

Configure transport mode via `MCP_TRANSPORT` environment variable.

## Usage

### Web Interface
1. Open `http://localhost:8000` in your browser
2. Click "Add Server" to add a new MCP server
3. Provide a GitHub URL for automatic analysis
4. Manage servers from the dashboard

### MCP Server Control
1. Navigate to "MCP Control" in the web UI
2. Select your desired transport mode:
   - **stdio**: For local Claude Desktop integration
   - **HTTP**: For remote access (Claude.ai, other clients)
   - **SSE**: Legacy server-sent events support
3. Configure host/port/path for HTTP transports
4. Click "Start Server" to launch the MCP server
5. Connection information is displayed automatically
6. Use "Stop Server" to shut down when done

### Claude Desktop Integration
1. Download configuration from the web UI
2. Place in Claude Desktop's configuration directory
3. Restart Claude Desktop

### Remote Access (HTTP)
Connect using any MCP client that supports HTTP transport:

```python
from fastmcp import Client

async with Client(
    "http://localhost:8001/mcp",
    api_key="your-api-key"
) as client:
    # Use the client
    tools = await client.list_tools()
```

## Architecture

MCP Router uses FastMCP's proxy feature to provide hierarchical tool discovery:

1. **Initial tools**: Only `python_sandbox` and `list_providers` are visible
2. **Discovery**: Call `list_providers()` to see available servers
3. **Server tools**: Use `tools/list(provider="server_name")` to see server-specific tools
4. **Execution**: Call tools with `provider` parameter for routing

This prevents tool overload while maintaining a clean, stateless architecture.

## Development Status

- ✅ **Week 1**: Foundation & Web UI (100% Complete)
- ✅ **Week 2**: Container & MCP Integration (95% Complete)
- ✅ **Week 3**: Claude Integration & Transport (100% Complete)
  - ✅ Claude repository analyzer
  - ✅ stdio transport
  - ✅ HTTP transport with authentication
- ⏳ **Week 4**: Testing & Deployment (0% Complete)

## Contributing

This is an MVP project with a 4-week development timeline. Contributions should align with the project roadmap outlined in `project.md`.

## License

[License information to be added] 