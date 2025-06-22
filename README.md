# MCP Router Tool

A Python-based MCP (Model Context Protocol) router that acts as a unified gateway for multiple MCP servers. The tool provides a web-based UI for managing MCP servers, automatically analyzes GitHub repositories using Claude to generate installation plans, and dynamically spawns containerized environments for each MCP server on-demand.

## Features

- **Web-based UI** for managing MCP servers
- **Automated repository analysis** using Claude AI
- **Dynamic container spawning** for MCP servers (Docker, NPX, UVX)
- **Multi-transport support** (stdio, SSE, HTTP)
- **Claude Desktop integration** for local development
- **Comprehensive monitoring** with Prometheus metrics
- **Health checks** and observability

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for container backend)
- Anthropic API key (for repository analysis)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd mcp-router
   ```

2. **Install dependencies:**
   ```bash
   pip install -e .
   ```

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Initialize the database:**
   ```bash
   python -m mcp_router --init-db
   ```

### Development Setup

1. **Install development dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

2. **Run the application:**
   ```bash
   python -m mcp_router
   ```

3. **Access the web UI:**
   Open http://localhost:8080 in your browser

## Configuration

### Environment Variables

Key configuration options:

- `ANTHROPIC_API_KEY` - Required for repository analysis
- `DATABASE_URL` - Database connection string (default: SQLite)
- `CONTAINER_BACKEND` - Container backend: `docker` or `e2b`
- `MCP_MODE` - Run mode: `local` (stdio) or `remote` (web server)

See `.env.example` for all available options.

### Claude Desktop Integration

For local Claude Desktop integration:

1. Get the configuration:
   ```bash
   curl http://localhost:8080/api/config/claude-desktop
   ```

2. Add the configuration to your Claude Desktop settings

## Project Status

🚧 **Currently in development** - Sprint 1 implementation includes:

- ✅ Project structure and configuration
- ✅ Database models and schemas
- ✅ FastAPI application skeleton
- ✅ Health check endpoints
- ✅ Basic API structure
- ✅ Logging and metrics setup
- 🚧 Server management (placeholder endpoints)
- 🚧 MCP protocol implementation (basic structure)
- 🚧 Container orchestration
- 🚧 Repository analysis with Claude
- 🚧 Web UI (React frontend)

### Implemented Components

#### Backend
- **Configuration Management** - Environment-based settings with validation
- **Database Layer** - SQLAlchemy models for servers, environment variables, audit logs
- **API Schema** - Comprehensive Pydantic schemas for request/response validation
- **Health Monitoring** - Database, container, and external service health checks
- **Metrics Collection** - Prometheus metrics for monitoring
- **Structured Logging** - JSON logging with rotation and levels

#### API Endpoints
- `GET /api/health` - Comprehensive health check
- `GET /api/health/live` - Kubernetes liveness probe
- `GET /api/health/ready` - Kubernetes readiness probe
- `GET /api/config/claude-desktop` - Claude Desktop configuration
- `GET /api/servers` - Server management (placeholder)
- `POST /mcp/*` - MCP protocol endpoints (placeholder)

### Next Steps (Sprint 2+)

1. **Container Integration** - Docker and E2B container management
2. **Claude Repository Analysis** - Automated MCP server configuration
3. **MCP Protocol Implementation** - Full FastMCP integration
4. **React Frontend** - Web UI for server management
5. **Transport Layer** - stdio, SSE, and HTTP transport adapters

## Testing

Run tests:
```bash
pytest
```

Run tests with coverage:
```bash
pytest --cov=mcp_router
```

## Architecture

### System Overview
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Claude Desktop │     │   Web Browser   │     │  Claude.ai API  │
│   (Local Mode)  │     │   (Admin UI)    │     │  (Remote Mode)  │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │ stdio                 │ HTTP                  │ HTTP/SSE
         │                       │                        │
┌────────┴───────────────────────┴────────────────────────┴────────┐
│                        MCP Router Service                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  FastAPI    │  │   FastMCP    │  │   Transport Manager    │  │
│  │  REST API   │  │   Router     │  │ (stdio/SSE/HTTP)       │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │   Claude    │  │   GitHub     │  │  Container Orchestrator │  │
│  │  Analyzer   │  │   Service    │  │   (Docker/E2B)         │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

### Database Schema
- **mcp_servers** - MCP server configurations
- **env_variables** - Environment variables for servers
- **audit_logs** - Change tracking and auditing
- **container_sessions** - Container lifecycle tracking

## Contributing

This project follows a sprint-based development approach. Current sprint focuses on foundational components and basic API structure.

### Code Standards
- Type hints on all functions
- Comprehensive docstrings
- Proper error handling and logging
- Centralized API functionality
- Rate limiting and retries for external APIs

## License

[MIT License](LICENSE) 