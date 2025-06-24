# MCP Router

MCP Router is a Python-based tool that acts as a unified gateway for multiple MCP (Model Context Protocol) servers. This project is structured as an installable Python package for easy development and deployment.

## Features (Week 1 - Foundation & Web UI)

- **Web UI**: Flask-based interface for server management.
- **Server CRUD**: Add, edit, delete, and toggle MCP servers.
- **Persistent Storage**: Uses SQLite for storing server configurations in a dedicated `data/` directory.
- **Deployable**: Packaged for deployment on services like Render, and for local use with Docker.
- **Claude Desktop Integration**: Generates a robust configuration for Claude Desktop.

## Project Structure

```
mcp-router/
├── .gitignore
├── .env.example
├── data/
│   └── .gitignore
├── docker-compose.yml
├── Dockerfile
├── project.md
├── pyproject.toml
├── README.md
├── src/
│   └── mcp_router/
│       ├── __init__.py
│       ├── __main__.py
│       └── ... (application modules)
└── tests/
    └── ... (test modules)
```

## Installation & Setup

### Prerequisites

- Python 3.11+
- A modern Python package manager like `pip` or `uv`.
- Docker (for containerized development).

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

Install the project in editable mode. This allows you to make code changes that are reflected immediately without reinstalling.

**Using `pip`:**
```bash
pip install -e .
```

**Using `uv`:**
```bash
uv pip install -e .
```

### 4. Configure Environment Variables

Copy the example `.env` file and fill in your secrets.

```bash
cp .env.example .env
# Open .env and add your keys
```
A `SECRET_KEY` is required. You can generate one with: `python -c 'import secrets; print(secrets.token_hex())'`

## Running the Application

This project has two primary entry points: the MCP server and the web UI.

### 1. Running the Web UI (for server management)

This command starts the Flask web server.

**As a Python Module:**
```bash
python -m mcp_router.web
```

**Using the script alias (after installation):**
```bash
mcp-router-web
```
The web interface will be available at `http://localhost:5001`.

### 2. Running the MCP Server (for Claude Desktop)

This command starts the FastMCP server that listens on stdio.

**As a Python Module:**
```bash
python -m mcp_router
```

**Using the script alias (after installation):**
```bash
mcp-router
```

### 3. Using Docker Compose

The `docker-compose.yml` is configured to run the **Web UI**.

```bash
docker-compose up --build
```

## Usage

- **Web Interface**: Open `http://localhost:5001` in your browser.
- **Adding a Server**: Navigate to "Add Server", provide a GitHub URL, and let the (placeholder) analyzer populate the form.
- **Managing Servers**: View, edit, test, and delete servers from the main dashboard and detail pages.
- **Claude Desktop**: Download the configuration file from the link on the home page.

## Development Status

### Week 1 (Complete) ✓
- Project setup and structure
- Flask web application
- Database models and forms
- Server CRUD operations
- Basic UI with Tailwind CSS and htmx
- Configuration validation

### Upcoming Features

**Week 2: Container & MCP Integration**
- Container management with llm-sandbox
- FastMCP server implementation
- Dynamic tool registration

**Week 3: Claude & Transport Support**
- Claude repository analyzer
- Transport implementations (stdio, HTTP)
- Real GitHub analysis

**Week 4: Testing & Deployment**
- Comprehensive testing
- Documentation
- Production deployment

## Configuration

The application uses environment variables for configuration. Key settings:

- `SECRET_KEY`: Flask secret key for sessions
- `ANTHROPIC_API_KEY`: For Claude analysis (Week 3)
- `GITHUB_TOKEN`: For GitHub API access (optional)
- `DATABASE_URL`: SQLite database path

## Contributing

This is an MVP project with a 4-week development timeline. Contributions should align with the project roadmap.

## License

[License information to be added] 