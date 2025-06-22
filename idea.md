# MCP Router Tool - Complete Requirements and Development Plan

## Original Requirements and Outline

### Project Description
I want to develop a tool in python that is a UX for adding and administering, as well as functioning as a router for MCP servers (https://gofastmcp.com/getting-started/welcome). The Model Context Protocol (MCP) is a new, standardized way to provide context and tools to your LLMs, and FastMCP makes building MCP servers and clients simple and intuitive. Create tools, expose resources, define prompts, and more with clean, Pythonic code.

The overall intuition of this tool is that it is a UX tool and service that allows you to add mcp servers via github url. The tool acts as an MCP server itself, and lists the added servers as tools. It loads the added MCP tools upon request in a containered environment and handles the IO between the LLM and tool.

### Core Requirements
1. Has a UX for adding and editing separate MCP servers.
2. New MCP servers can be added by github URL but supports npx, uvx, and docker.
3. Uses claude (https://github.com/anthropics/anthropic-sdk-python) to read github readme, and define an install and serving plan.
4. Supports: sse, stdio, and streamable http forms of MCP
5. Can be connected to Claude Desktop locally, or can be deployed to serve an endpoint that can be added to Claude to access the router tools.
6. The library FastMCP at https://gofastmcp.com/getting-started/welcome is a well done implementation of MCP and could be used for support for specific requirements.
7. We launch the services when requested into a containered environment because we need to support typescript, python, and other environments.
8. The tool should supply a field with any ENV variables with keys that need to be added, based on what was parsed out of the github url. This will be used when the individual mcp tool is called.
9. We should have a default sandbox tool in python with main libraries like pandas, numpy, etc installed that can be used as a tool to send code to to get the result.

### Additional Context
- Container spawning: on-demand per request (with potential startup delays)
- Container persistence: fresh containers for each session
- Development timeline: 4 weeks, 1 developer, 1-week sprints
- Suggested library: https://github.com/vndee/llm-sandbox for npx, uvx, and docker sandboxes

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

---

## Complete Development Plan

### System Description
A Python-based MCP (Model Context Protocol) router that acts as a unified gateway for multiple MCP servers. The tool provides a web-based UI for managing MCP servers, automatically analyzes GitHub repositories using Claude to generate installation plans, and dynamically spawns containerized environments for each MCP server on-demand. The router itself functions as an MCP server, exposing all registered servers' tools through a single interface.

### Core Components
1. **Web UI** - React-based interface for server management
2. **MCP Router** - FastMCP-based routing engine
3. **Container Manager** - llm-sandbox integration for multi-runtime support
4. **Claude Analyzer** - Automated repository analysis and setup
5. **Transport Bridge** - Multi-protocol support (stdio, SSE, HTTP)
6. **Configuration Manager** - Claude Desktop and deployment configs

## Technical Architecture

### System Architecture Diagram
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Claude Desktop │     │   Web Browser   │     │  Claude.ai API  │
│   (Local Mode)  │     │   (Admin UI)    │     │  (Remote Mode)  │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                        │
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
│  │  Analyzer   │  │   Service    │  │   (llm-sandbox)        │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
┌────────▼────────┐   ┌─────────▼────────┐   ┌────────▼────────┐
│ NPX Container   │   │  UVX Container   │   │ Docker Container│
│ (Node.js MCP)   │   │  (Python MCP)    │   │  (Custom MCP)   │
└─────────────────┘   └──────────────────┘   └─────────────────┘
```

### Technology Stack

#### Backend
- **Python 3.11+** - Core language
- **FastAPI** - REST API and web server
- **FastMCP** - MCP protocol implementation
- **llm-sandbox** - Container runtime management
- **anthropic-sdk-python** - Claude integration
- **SQLAlchemy + SQLite** - Database
- **Pydantic** - Data validation
- **httpx** - Async HTTP client
- **structlog** - Structured logging
- **pytest + pytest-asyncio** - Testing
- **loguru** - logging

#### Frontend
- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **TailwindCSS** - Styling
- **React Query** - API state management
- **React Hook Form** - Form handling
- **Monaco Editor** - Code display

#### Infrastructure
- **Docker** - Containerization
- **Docker Compose** - Local development
- **E2B** - Cloud container runtime (optional)
- **Prometheus + Grafana** - Monitoring

## Database Schema

```sql
-- MCP Servers table
CREATE TABLE mcp_servers (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    github_url TEXT NOT NULL,
    description TEXT,
    runtime_type TEXT NOT NULL CHECK(runtime_type IN ('npx', 'uvx', 'docker')),
    install_command TEXT NOT NULL,
    start_command TEXT NOT NULL,
    transport_type TEXT NOT NULL CHECK(transport_type IN ('stdio', 'sse', 'http')),
    transport_config JSON NOT NULL,
    env_variables JSON NOT NULL DEFAULT '[]',
    capabilities JSON NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_healthy BOOLEAN NOT NULL DEFAULT false,
    last_health_check TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Environment Variables table (normalized)
CREATE TABLE env_variables (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    server_id TEXT NOT NULL,
    key TEXT NOT NULL,
    description TEXT,
    is_required BOOLEAN NOT NULL DEFAULT true,
    is_secret BOOLEAN NOT NULL DEFAULT false,
    default_value TEXT,
    validation_regex TEXT,
    FOREIGN KEY (server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE,
    UNIQUE(server_id, key)
);

-- Audit Log table
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    details JSON,
    user_id TEXT,
    ip_address TEXT
);

-- Container Sessions table
CREATE TABLE container_sessions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    server_id TEXT NOT NULL,
    container_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('starting', 'running', 'stopping', 'stopped', 'error')),
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP,
    metrics JSON,
    FOREIGN KEY (server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE
);
```

## API Specification

### REST API Endpoints

```yaml
# Server Management
POST   /api/servers/analyze
  Request:
    github_url: string
  Response:
    name: string
    description: string
    runtime_type: 'npx' | 'uvx' | 'docker'
    install_command: string
    start_command: string
    env_variables: Array<{key: string, description: string, required: boolean}>
    detected_tools: Array<string>

POST   /api/servers
  Request:
    name: string
    github_url: string
    runtime_type: string
    install_command: string
    start_command: string
    transport_type: string
    transport_config: object
    env_variables: Array<EnvVariable>

GET    /api/servers
  Response:
    servers: Array<Server>

GET    /api/servers/{id}
  Response: Server

PUT    /api/servers/{id}
  Request: Partial<Server>
  Response: Server

DELETE /api/servers/{id}
  Response: {success: boolean}

POST   /api/servers/{id}/test
  Response:
    success: boolean
    error?: string
    capabilities?: object

GET    /api/servers/{id}/logs
  Query:
    lines?: number = 100
    since?: timestamp
  Response:
    logs: Array<LogEntry>

# Environment Variables
PUT    /api/servers/{id}/env/{key}
  Request:
    value: string
  Response: {success: boolean}

# System
GET    /api/health
  Response:
    status: 'healthy' | 'degraded' | 'unhealthy'
    services: object

GET    /api/config/claude-desktop
  Response:
    config: object  # claude_desktop_config.json content

# MCP Protocol Endpoints (FastMCP handles these)
POST   /mcp/initialize
POST   /mcp/initialized
POST   /mcp/tools/list
POST   /mcp/tools/call
POST   /mcp/resources/list
POST   /mcp/resources/read
POST   /mcp/prompts/list
POST   /mcp/prompts/get
POST   /mcp/completion/complete
```

### MCP Protocol Implementation

```python
# Core MCP Router using FastMCP
from fastmcp import FastMCP, Tool, Resource
from typing import Dict, Any, List

class MCPRouterServer:
    def __init__(self, db_service: DatabaseService, container_service: ContainerService):
        self.mcp = FastMCP("MCP Router")
        self.db = db_service
        self.containers = container_service
        self._setup_default_tools()
        
    def _setup_default_tools(self):
        """Register default Python sandbox tool"""
        @self.mcp.tool()
        async def python_sandbox(code: str) -> Dict[str, Any]:
            """Execute Python code in a sandboxed environment with data science libraries"""
            result = await self.containers.execute_in_sandbox(
                runtime="python",
                code=code,
                libraries=["pandas", "numpy", "scipy", "matplotlib", "seaborn"]
            )
            return {
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.exit_code
            }
    
    async def refresh_tools(self):
        """Dynamically load tools from all active servers"""
        servers = await self.db.get_active_servers()
        
        for server in servers:
            # Create a dynamic tool that proxies to the containerized server
            tool_func = self._create_proxy_tool(server)
            self.mcp.tool(name=f"{server.name}_tool")(tool_func)
    
    def _create_proxy_tool(self, server: MCPServer):
        async def proxy_tool(**kwargs) -> Any:
            # Spawn container for this server
            container = await self.containers.spawn_container(
                server_id=server.id,
                runtime_type=server.runtime_type,
                env_vars=server.get_env_dict()
            )
            
            try:
                # Forward the tool call to the container
                result = await container.call_tool(kwargs)
                return result
            finally:
                # Clean up container after use
                await container.cleanup()
        
        return proxy_tool
```

## Container Management Strategy

### Runtime Detection and Execution

```python
class ContainerRuntimeDetector:
    """Detects appropriate runtime from GitHub repository"""
    
    async def detect_runtime(self, repo_files: List[str]) -> RuntimeInfo:
        if "package.json" in repo_files:
            return RuntimeInfo(
                type="npx",
                install_command="npm install",
                start_command="npx -y {package_name}"
            )
        elif "pyproject.toml" in repo_files or "setup.py" in repo_files:
            return RuntimeInfo(
                type="uvx",
                install_command="pip install -e .",
                start_command="uvx {package_name}"
            )
        elif "Dockerfile" in repo_files:
            return RuntimeInfo(
                type="docker",
                install_command="docker build -t {name} .",
                start_command="docker run --rm -i {name}"
            )
        else:
            # Fallback to analyzing file extensions
            # ...

class ContainerOrchestrator:
    """Manages container lifecycle using llm-sandbox"""
    
    def __init__(self, config: ContainerConfig):
        self.sandbox_manager = SandboxManager(config)
        self.active_containers: Dict[str, Container] = {}
        
    async def spawn_container(
        self, 
        server_id: str,
        runtime_type: str,
        env_vars: Dict[str, str]
    ) -> Container:
        """Spawn a fresh container for the MCP server"""
        
        # Use llm-sandbox to create appropriate container
        if runtime_type == "npx":
            sandbox = NodejsSandbox(
                max_execution_time=300,
                memory_limit="512m",
                env_vars=env_vars
            )
        elif runtime_type == "uvx":
            sandbox = PythonSandbox(
                max_execution_time=300,
                memory_limit="512m",
                env_vars=env_vars
            )
        elif runtime_type == "docker":
            sandbox = DockerSandbox(
                image=f"mcp-{server_id}",
                max_execution_time=300,
                memory_limit="512m",
                env_vars=env_vars
            )
        
        container = await sandbox.start()
        self.active_containers[container.id] = container
        
        return container
```

## Claude Integration for Repository Analysis

```python
from anthropic import AsyncAnthropic
import base64

class ClaudeRepositoryAnalyzer:
    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)
        
    async def analyze_repository(self, github_url: str) -> ServerConfiguration:
        """Use Claude to analyze repository and generate configuration"""
        
        # Fetch repository content
        repo_content = await self._fetch_repo_content(github_url)
        
        # Prepare context for Claude
        context = f"""
        Analyze this GitHub repository for MCP server setup:
        
        Repository: {github_url}
        
        README.md:
        {repo_content.readme}
        
        Package files:
        {repo_content.package_files}
        
        Please determine:
        1. The appropriate runtime (npx for Node.js, uvx for Python, docker if Dockerfile exists)
        2. Installation commands needed
        3. The command to start the MCP server
        4. Required environment variables (look for mentions of API keys, tokens, etc.)
        5. What tools/capabilities this MCP server provides
        6. A brief description of what this server does
        """
        
        response = await self.client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1500,
            temperature=0,
            system="You are an expert at analyzing MCP (Model Context Protocol) servers. Extract configuration details accurately.",
            messages=[{
                "role": "user",
                "content": context
            }]
        )
        
        # Parse Claude's response into structured data
        config = self._parse_claude_response(response.content)
        
        return ServerConfiguration(
            name=self._extract_name_from_url(github_url),
            github_url=github_url,
            runtime_type=config['runtime'],
            install_command=config['install_command'],
            start_command=config['start_command'],
            env_variables=config['env_variables'],
            description=config['description'],
            capabilities=config['capabilities']
        )
    
    def _parse_claude_response(self, content: str) -> Dict[str, Any]:
        """Parse Claude's response into structured configuration"""
        # Use regex or structured parsing to extract:
        # - Runtime type
        # - Commands
        # - Environment variables with descriptions
        # - Tool capabilities
        # ...
```

## Web UI Implementation

### React Component Structure

```typescript
// Main App Structure
src/
├── components/
│   ├── ServerList/
│   │   ├── ServerList.tsx
│   │   ├── ServerCard.tsx
│   │   └── ServerStatus.tsx
│   ├── ServerForm/
│   │   ├── AddServerModal.tsx
│   │   ├── GitHubUrlInput.tsx
│   │   ├── EnvVariableForm.tsx
│   │   └── InstallationPreview.tsx
│   ├── ServerDetail/
│   │   ├── ServerDetailView.tsx
│   │   ├── ServerLogs.tsx
│   │   ├── ServerMetrics.tsx
│   │   └── TestConnection.tsx
│   └── Common/
│       ├── Layout.tsx
│       ├── LoadingSpinner.tsx
│       └── ErrorBoundary.tsx
├── hooks/
│   ├── useServers.ts
│   ├── useServerAnalysis.ts
│   └── useWebSocket.ts
├── services/
│   ├── api.ts
│   ├── websocket.ts
│   └── types.ts
└── App.tsx

// Example Component: Add Server Modal
interface AddServerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (server: Server) => void;
}

export function AddServerModal({ isOpen, onClose, onSuccess }: AddServerModalProps) {
  const [githubUrl, setGithubUrl] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  
  const analyzeRepository = async () => {
    setAnalyzing(true);
    try {
      const result = await api.analyzeRepository(githubUrl);
      setConfig(result);
      
      // Initialize env values with defaults
      const defaultEnvs: Record<string, string> = {};
      result.env_variables.forEach(env => {
        defaultEnvs[env.key] = env.default_value || '';
      });
      setEnvValues(defaultEnvs);
    } catch (error) {
      toast.error('Failed to analyze repository');
    } finally {
      setAnalyzing(false);
    }
  };
  
  const handleSubmit = async () => {
    if (!config) return;
    
    try {
      const server = await api.createServer({
        ...config,
        env_variables: Object.entries(envValues).map(([key, value]) => ({
          key,
          value,
          is_secret: config.env_variables.find(e => e.key === key)?.is_secret || false
        }))
      });
      
      onSuccess(server);
      onClose();
    } catch (error) {
      toast.error('Failed to create server');
    }
  };
  
  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <div className="p-6">
        <h2 className="text-2xl font-bold mb-4">Add MCP Server</h2>
        
        {/* Step 1: GitHub URL Input */}
        {!config && (
          <div>
            <label className="block text-sm font-medium mb-2">
              GitHub Repository URL
            </label>
            <div className="flex gap-2">
              <input
                type="url"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="flex-1 px-3 py-2 border rounded-md"
              />
              <button
                onClick={analyzeRepository}
                disabled={!githubUrl || analyzing}
                className="px-4 py-2 bg-blue-500 text-white rounded-md"
              >
                {analyzing ? <Spinner /> : 'Analyze'}
              </button>
            </div>
          </div>
        )}
        
        {/* Step 2: Configuration Review */}
        {config && (
          <div className="space-y-4">
            <div className="bg-gray-50 p-4 rounded-md">
              <h3 className="font-semibold">{config.name}</h3>
              <p className="text-sm text-gray-600">{config.description}</p>
              <div className="mt-2 flex gap-2">
                <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">
                  {config.runtime_type}
                </span>
                <span className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs">
                  {config.transport_type}
                </span>
              </div>
            </div>
            
            {/* Environment Variables */}
            {config.env_variables.length > 0 && (
              <div>
                <h4 className="font-medium mb-2">Environment Variables</h4>
                <div className="space-y-2">
                  {config.env_variables.map(env => (
                    <div key={env.key}>
                      <label className="block text-sm">
                        {env.key}
                        {env.is_required && <span className="text-red-500">*</span>}
                      </label>
                      <input
                        type={env.is_secret ? 'password' : 'text'}
                        value={envValues[env.key] || ''}
                        onChange={(e) => setEnvValues({
                          ...envValues,
                          [env.key]: e.target.value
                        })}
                        placeholder={env.description}
                        className="w-full px-3 py-1 border rounded-md"
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Installation Preview */}
            <div>
              <h4 className="font-medium mb-2">Installation Plan</h4>
              <pre className="bg-gray-900 text-gray-100 p-3 rounded-md text-sm">
                {config.install_command}
              </pre>
            </div>
            
            <div className="flex justify-end gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 border rounded-md"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                className="px-4 py-2 bg-green-500 text-white rounded-md"
              >
                Add Server
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
```

## Transport Layer Implementation

### Multi-Transport Support

```python
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator
import asyncio
import httpx

class TransportAdapter(ABC):
    """Base class for MCP transport adapters"""
    
    @abstractmethod
    async def connect(self) -> None:
        pass
    
    @abstractmethod
    async def send_request(self, method: str, params: Any) -> Any:
        pass
    
    @abstractmethod
    async def close(self) -> None:
        pass

class StdioTransportAdapter(TransportAdapter):
    """Handles stdio-based MCP communication"""
    
    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self.reader = asyncio.StreamReader()
        self.writer = process.stdin
        
    async def connect(self) -> None:
        # Set up async reading from stdout
        asyncio.create_task(self._read_output())
        
    async def send_request(self, method: str, params: Any) -> Any:
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": str(uuid.uuid4())
        }
        
        # Write to stdin
        self.writer.write(json.dumps(request).encode() + b'\n')
        await self.writer.drain()
        
        # Wait for response
        response = await self._wait_for_response(request["id"])
        return response

class SSETransportAdapter(TransportAdapter):
    """Handles Server-Sent Events MCP communication"""
    
    def __init__(self, url: str, headers: Dict[str, str] = None):
        self.url = url
        self.headers = headers or {}
        self.client = httpx.AsyncClient()
        
    async def connect(self) -> None:
        # Establish SSE connection
        self.event_source = await self.client.stream(
            'GET', 
            f"{self.url}/sse",
            headers=self.headers
        )
        
    async def send_request(self, method: str, params: Any) -> Any:
        response = await self.client.post(
            f"{self.url}/mcp/{method}",
            json=params,
            headers=self.headers
        )
        return response.json()

class HTTPTransportAdapter(TransportAdapter):
    """Handles HTTP-based MCP communication"""
    
    def __init__(self, url: str, headers: Dict[str, str] = None):
        self.url = url
        self.headers = headers or {}
        self.client = httpx.AsyncClient()
        
    async def send_request(self, method: str, params: Any) -> Any:
        response = await self.client.post(
            f"{self.url}/mcp/{method}",
            json={
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": str(uuid.uuid4())
            },
            headers=self.headers
        )
        return response.json()

class TransportManager:
    """Manages transport adapters for different MCP servers"""
    
    def __init__(self):
        self.adapters: Dict[str, TransportAdapter] = {}
        
    async def create_adapter(
        self, 
        server: MCPServer, 
        container: Container
    ) -> TransportAdapter:
        """Create appropriate transport adapter for server"""
        
        if server.transport_type == "stdio":
            # Get the process from container
            process = await container.get_process()
            adapter = StdioTransportAdapter(process)
            
        elif server.transport_type == "sse":
            # Get the HTTP endpoint from container
            endpoint = await container.get_endpoint()
            adapter = SSETransportAdapter(
                url=endpoint,
                headers={"Authorization": f"Bearer {container.auth_token}"}
            )
            
        elif server.transport_type == "http":
            endpoint = await container.get_endpoint()
            adapter = HTTPTransportAdapter(
                url=endpoint,
                headers={"Authorization": f"Bearer {container.auth_token}"}
            )
            
        await adapter.connect()
        self.adapters[server.id] = adapter
        
        return adapter
```

## Claude Desktop Integration

### Configuration Generator

```python
class ClaudeDesktopConfigGenerator:
    """Generates claude_desktop_config.json for local integration"""
    
    def generate_config(self, router_config: RouterConfig) -> Dict[str, Any]:
        if router_config.mode == "local":
            # Local stdio mode for Claude Desktop
            return {
                "mcpServers": {
                    "mcp-router": {
                        "command": "python",
                        "args": [
                            "-m",
                            "mcp_router",
                            "--mode",
                            "stdio"
                        ],
                        "env": {
                            "MCP_ROUTER_DB": str(router_config.db_path),
                            "MCP_ROUTER_CACHE": str(router_config.cache_path)
                        }
                    }
                }
            }
        else:
            # Remote HTTP mode
            return {
                "mcpServers": {
                    "mcp-router": {
                        "url": router_config.remote_url,
                        "transport": "sse",
                        "headers": {
                            "Authorization": f"Bearer {router_config.api_key}"
                        }
                    }
                }
            }
    
    def save_config(self, config: Dict[str, Any], path: Path = None):
        """Save config to Claude Desktop configuration directory"""
        if path is None:
            # Default Claude Desktop config location
            if sys.platform == "darwin":  # macOS
                path = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
            elif sys.platform == "win32":  # Windows
                path = Path.home() / "AppData/Roaming/Claude/claude_desktop_config.json"
            else:  # Linux
                path = Path.home() / ".config/claude/claude_desktop_config.json"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Merge with existing config if present
        existing = {}
        if path.exists():
            existing = json.loads(path.read_text())
        
        existing.update(config)
        path.write_text(json.dumps(existing, indent=2))
```

## Default Python Sandbox Implementation

```python
class PythonSandboxTool:
    """Built-in Python sandbox with data science libraries"""
    
    DEFAULT_IMPORTS = """
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import scipy
import sklearn
from io import StringIO
import json
import requests
import datetime
"""
    
    def __init__(self, container_manager: ContainerOrchestrator):
        self.container_manager = container_manager
        self.sandbox_image = "mcp-router/python-sandbox:latest"
        
    async def execute_code(self, code: str) -> Dict[str, Any]:
        """Execute Python code in sandboxed environment"""
        
        # Prepend default imports
        full_code = self.DEFAULT_IMPORTS + "\n\n" + code
        
        # Create temporary container
        container = await self.container_manager.spawn_container(
            server_id="python-sandbox",
            runtime_type="docker",
            env_vars={
                "PYTHONUNBUFFERED": "1",
                "MPLBACKEND": "Agg"  # Non-interactive matplotlib backend
            }
        )
        
        try:
            # Execute code
            result = await container.execute(
                command=["python", "-c", full_code],
                timeout=30
            )
            
            # Capture any generated plots
            plots = await self._extract_plots(container)
            
            return {
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.exit_code,
                "plots": plots
            }
            
        finally:
            await container.cleanup()
    
    async def _extract_plots(self, container: Container) -> List[str]:
        """Extract matplotlib plots as base64 images"""
        plots = []
        
        # Check for saved plots in container
        plot_files = await container.list_files("/tmp/plots/")
        
        for file in plot_files:
            if file.endswith(('.png', '.jpg', '.svg')):
                content = await container.read_file(file)
                plots.append({
                    "filename": file,
                    "data": base64.b64encode(content).decode()
                })
        
        return plots
```

## Monitoring and Observability

```python
from prometheus_client import Counter, Histogram, Gauge, Info
import structlog

# Metrics
mcp_requests_total = Counter(
    'mcp_requests_total',
    'Total MCP requests',
    ['server', 'method', 'status']
)

mcp_request_duration = Histogram(
    'mcp_request_duration_seconds',
    'MCP request duration',
    ['server', 'method']
)

active_containers = Gauge(
    'mcp_active_containers',
    'Number of active containers',
    ['runtime_type']
)

server_info = Info(
    'mcp_server_info',
    'Information about MCP servers'
)

# Structured logging
logger = structlog.get_logger()

class MetricsMiddleware:
    """FastAPI middleware for metrics collection"""
    
    async def __call__(self, request: Request, call_next):
        start_time = time.time()
        
        # Extract metadata
        path = request.url.path
        method = request.method
        
        # Log request
        logger.info(
            "http_request_started",
            path=path,
            method=method,
            client_ip=request.client.host
        )
        
        try:
            response = await call_next(request)
            
            # Record metrics
            duration = time.time() - start_time
            
            logger.info(
                "http_request_completed",
                path=path,
                method=method,
                status_code=response.status_code,
                duration=duration
            )
            
            return response
            
        except Exception as e:
            logger.error(
                "http_request_failed",
                path=path,
                method=method,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
```

## Security Implementation

```python
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

class SecurityConfig:
    """Security configuration and utilities"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bearer_scheme = HTTPBearer()
        
    async def verify_token(
        self, 
        credentials: HTTPAuthorizationCredentials = Security(HTTPBearer())
    ) -> Dict[str, Any]:
        """Verify JWT token for API access"""
        
        token = credentials.credentials
        
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=["HS256"]
            )
            
            # Verify token hasn't expired
            if payload.get("exp", 0) < time.time():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired"
                )
            
            return payload
            
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token"
            )
    
    def generate_api_key(self, user_id: str) -> str:
        """Generate API key for remote access"""
        
        payload = {
            "sub": user_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + 86400 * 365,  # 1 year
            "type": "api_key"
        }
        
        return jwt.encode(payload, self.settings.jwt_secret, algorithm="HS256")

class ContainerSecurityPolicy:
    """Security policies for containers"""
    
    @staticmethod
    def get_docker_security_opts() -> List[str]:
        return [
            "--cap-drop=ALL",
            "--cap-add=NET_BIND_SERVICE",
            "--read-only",
            "--security-opt=no-new-privileges:true",
            "--pids-limit=100",
            "--memory=512m",
            "--cpus=1.0"
        ]
    
    @staticmethod
    def get_seccomp_profile() -> Dict[str, Any]:
        """Restrictive seccomp profile for containers"""
        return {
            "defaultAction": "SCMP_ACT_ERRNO",
            "architectures": ["SCMP_ARCH_X86_64"],
            "syscalls": [
                {
                    "names": [
                        "read", "write", "close", "stat", "fstat",
                        "lstat", "poll", "lseek", "mmap", "mprotect",
                        "munmap", "brk", "rt_sigaction", "rt_sigprocmask",
                        "rt_sigreturn", "ioctl", "pread64", "pwrite64",
                        "readv", "writev", "access", "pipe", "select"
                        # ... minimal syscalls needed
                    ],
                    "action": "SCMP_ACT_ALLOW"
                }
            ]
        }
```

## Testing Strategy

### Unit Tests

```python
# tests/test_router.py
import pytest
from unittest.mock import Mock, AsyncMock
from mcp_router.core import MCPRouterServer

@pytest.fixture
def mock_db_service():
    service = Mock()
    service.get_active_servers = AsyncMock(return_value=[
        MCPServer(
            id="test-1",
            name="test-server",
            runtime_type="npx",
            transport_type="stdio"
        )
    ])
    return service

@pytest.fixture
def mock_container_service():
    service = Mock()
    service.spawn_container = AsyncMock()
    return service

@pytest.mark.asyncio
async def test_router_initialization(mock_db_service, mock_container_service):
    """Test MCP router initializes correctly"""
    router = MCPRouterServer(mock_db_service, mock_container_service)
    
    # Verify default tools are registered
    tools = await router.mcp.list_tools()
    assert any(tool.name == "python_sandbox" for tool in tools)

@pytest.mark.asyncio
async def test_proxy_tool_creation(mock_db_service, mock_container_service):
    """Test dynamic proxy tool creation"""
    router = MCPRouterServer(mock_db_service, mock_container_service)
    
    # Refresh tools from database
    await router.refresh_tools()
    
    # Verify proxy tool was created
    tools = await router.mcp.list_tools()
    assert any(tool.name == "test-server_tool" for tool in tools)

# tests/test_container_manager.py
@pytest.mark.asyncio
async def test_container_spawn_and_cleanup():
    """Test container lifecycle management"""
    manager = ContainerOrchestrator(ContainerConfig())
    
    # Spawn container
    container = await manager.spawn_container(
        server_id="test",
        runtime_type="python",
        env_vars={"TEST": "value"}
    )
    
    assert container.id in manager.active_containers
    
    # Cleanup
    await container.cleanup()
    
    assert container.id not in manager.active_containers
```

### Integration Tests

```python
# tests/integration/test_e2e_flow.py
import httpx
import asyncio
from testcontainers.compose import DockerCompose

@pytest.mark.integration
async def test_complete_server_addition_flow():
    """Test adding and using an MCP server end-to-end"""
    
    async with httpx.AsyncClient(base_url="http://localhost:8080") as client:
        # 1. Analyze GitHub repository
        analysis = await client.post("/api/servers/analyze", json={
            "github_url": "https://github.com/example/test-mcp-server"
        })
        assert analysis.status_code == 200
        
        config = analysis.json()
        
        # 2. Create server with configuration
        server_response = await client.post("/api/servers", json={
            **config,
            "env_variables": [
                {"key": "API_KEY", "value": "test-key"}
            ]
        })
        assert server_response.status_code == 201
        
        server = server_response.json()
        
        # 3. Test server connection
        test_response = await client.post(f"/api/servers/{server['id']}/test")
        assert test_response.status_code == 200
        assert test_response.json()["success"]
        
        # 4. Use server through MCP protocol
        mcp_response = await client.post("/mcp/tools/list")
        tools = mcp_response.json()["tools"]
        
        # Verify our server's tools are available
        server_tools = [t for t in tools if t["name"].startswith(server["name"])]
        assert len(server_tools) > 0
```

## Deployment Configuration

### Docker Compose Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  mcp-router:
    build: .
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=sqlite:///data/mcp_router.db
      - E2B_API_KEY=${E2B_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
    volumes:
      - ./data:/data
      - /var/run/docker.sock:/var/run/docker.sock  # For Docker-in-Docker
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources

volumes:
  redis-data:
  prometheus-data:
  grafana-data:

# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    docker.io \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Build frontend
WORKDIR /app/frontend
RUN npm install && npm run build

WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /app
USER mcp

# Expose ports
EXPOSE 8080

# Run application
CMD ["python", "-m", "mcp_router", "--host", "0.0.0.0", "--port", "8080"]
```

## Sprint-by-Sprint Detailed Plan

### Sprint 1: Foundation & Web UI (Week 1)

**Day 1-2: Project Setup & Database**
- Initialize Python project with proper structure
- Set up SQLAlchemy models and database migrations
- Create Pydantic schemas for validation
- Implement basic FastAPI application skeleton
- Set up pytest and testing infrastructure

**Day 3-4: Web UI Foundation**
- Create React application with TypeScript
- Implement server list view with mock data
- Build add server modal with form validation
- Create API client service for frontend
- Implement basic routing and layout

**Day 5: Integration**
- Connect frontend to backend APIs
- Implement server CRUD operations
- Add error handling and loading states
- Basic authentication setup
- End-to-end testing

**Deliverables:**
- Working web UI for server management
- Database persistence for configurations
- Basic API structure established

### Sprint 2: Container Integration & MCP Core (Week 2)

**Day 1-2: Container Management**
- Integrate llm-sandbox library
- Implement runtime detection logic
- Create container lifecycle manager
- Add resource limits and security policies

**Day 3-4: MCP Router Implementation**
- Set up FastMCP server structure
- Implement dynamic tool registration
- Create proxy tool mechanism
- Add default Python sandbox tool

**Day 5: Transport Layer**
- Implement stdio transport adapter
- Add basic HTTP transport support
- Create transport manager
- Integration testing with containers

**Deliverables:**
- Container spawning for all runtime types
- Basic MCP routing functionality
- Python sandbox tool working

### Sprint 3: Claude Integration & Advanced Features (Week 3)

**Day 1-2: Claude Repository Analysis**
- Integrate Anthropic SDK
- Implement repository fetching from GitHub
- Create Claude prompt templates
- Parse analysis results into configurations

**Day 3-4: Transport Completion**
- Implement SSE transport adapter
- Add transport auto-detection
- Create connection pooling
- Implement circuit breaker pattern

**Day 5: Claude Desktop Integration**
- Create configuration generator
- Add local/remote mode support
- Implement setup instructions UI
- Test with Claude Desktop

**Deliverables:**
- Automated repository analysis
- All transport types supported
- Claude Desktop integration working

### Sprint 4: Production Features & Polish (Week 4)

**Day 1-2: Security & Monitoring**
- Implement JWT authentication
- Add API key generation
- Set up Prometheus metrics
- Create Grafana dashboards

**Day 3-4: Testing & Documentation**
- Comprehensive integration tests
- Load testing with multiple containers
- API documentation with OpenAPI
- User guide and setup instructions

**Day 5: Deployment & Optimization**
- Docker image optimization
- Production deployment scripts
- Performance tuning
- Final bug fixes

**Deliverables:**
- Production-ready application
- Complete documentation
- Monitoring and observability
- Deployment packages

## Configuration Files

### Settings Configuration

```python
# mcp_router/config/settings.py
from pydantic import BaseSettings, Field
from typing import Optional, Literal
from pathlib import Path

class Settings(BaseSettings):
    # Application
    app_name: str = "MCP Router"
    debug: bool = Field(False, env="DEBUG")
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8080, env="PORT")
    
    # Database
    database_url: str = Field(
        "sqlite:///./data/mcp_router.db",
        env="DATABASE_URL"
    )
    
    # Security
    secret_key: str = Field(..., env="SECRET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_expiration: int = 86400  # 24 hours
    
    # External Services
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    github_token: Optional[str] = Field(None, env="GITHUB_TOKEN")
    e2b_api_key: Optional[str] = Field(None, env="E2B_API_KEY")
    
    # Container Configuration
    container_backend: Literal["docker", "e2b"] = Field(
        "docker",
        env="CONTAINER_BACKEND"
    )
    max_concurrent_containers: int = Field(10, env="MAX_CONTAINERS")
    container_timeout: int = Field(300, env="CONTAINER_TIMEOUT")
    container_memory_limit: str = Field("512m", env="CONTAINER_MEMORY")
    container_cpu_limit: float = Field(1.0, env="CONTAINER_CPU")
    
    # MCP Configuration
    mcp_mode: Literal["local", "remote"] = Field("local", env="MCP_MODE")
    mcp_remote_url: Optional[str] = Field(None, env="MCP_REMOTE_URL")
    
    # Cache
    redis_url: Optional[str] = Field(None, env="REDIS_URL")
    cache_ttl: int = Field(3600, env="CACHE_TTL")
    
    # Monitoring
    enable_metrics: bool = Field(True, env="ENABLE_METRICS")
    metrics_port: int = Field(9090, env="METRICS_PORT")
    
    # Paths
    data_dir: Path = Field(Path("./data"), env="DATA_DIR")
    log_dir: Path = Field(Path("./logs"), env="LOG_DIR")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories
        self.data_dir.mkdir(exist_ok=True)
        self.log_dir.mkdir(exist_ok=True)
```

### Requirements File

```txt
# requirements.txt
# Core
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
python-dotenv==1.0.0

# MCP
fastmcp==2.0.0

# Database
sqlalchemy==2.0.23
alembic==1.12.1
aiosqlite==0.19.0

# Container Management
llm-sandbox==0.1.0
docker==6.1.3
aiodocker==0.21.0

# External Services
anthropic==0.8.0
httpx==0.25.1
PyGithub==2.1.1

# Authentication & Security
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6

# Monitoring
prometheus-client==0.19.0
structlog==23.2.0
python-json-logger==2.0.7

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
testcontainers==3.7.1
httpx[cli]==0.25.1

# Utilities
tenacity==8.2.3
asyncio-throttle==1.0.2
cachetools==5.3.2
```

## Project Structure

```
mcp-router/
├── backend/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── servers.py         # Server management endpoints
│   │   │   ├── mcp.py            # MCP protocol endpoints
│   │   │   ├── health.py         # Health check endpoints
│   │   │   └── config.py         # Configuration endpoints
│   │   └── dependencies.py        # FastAPI dependencies
│   ├── core/
│   │   ├── __init__.py
│   │   ├── router.py             # MCP router implementation
│   │   ├── registry.py           # Server registry
│   │   └── auth.py               # Authentication logic
│   ├── services/
│   │   ├── __init__.py
│   │   ├── claude_analyzer.py    # Claude repository analysis
│   │   ├── github_service.py     # GitHub integration
│   │   ├── container_manager.py  # Container orchestration
│   │   └── transport_manager.py  # Transport adapters
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py           # SQLAlchemy models
│   │   └── schemas.py            # Pydantic schemas
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py           # Application settings
│   └── utils/
│       ├── __init__.py
│       ├── logging.py            # Logging configuration
│       └── metrics.py            # Prometheus metrics
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── styles/
│   │   └── types/
│   └── public/
├── tests/
│   ├── __init__.py
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── deployment/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   ├── Dockerfile
│   ├── prometheus.yml
│   └── grafana/
├── docs/
│   ├── README.md
│   ├── API.md
│   ├── DEPLOYMENT.md
│   └── USER_GUIDE.md
├── scripts/
│   ├── setup.sh
│   ├── test.sh
│   └── deploy.sh
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── README.md
```

## Summary

This comprehensive plan provides:

1. **Complete feature coverage** - All 9 requirements addressed with implementation details
2. **Clear architecture** - Modular design with separation of concerns
3. **Practical sprint planning** - Daily tasks for a single developer
4. **Production readiness** - Security, monitoring, and deployment
5. **Extensive code examples** - Real implementation patterns
6. **Testing strategy** - Unit, integration, and E2E tests
7. **Documentation** - API specs, user guides, and deployment instructions
8. **Configuration management** - Environment-based settings
9. **Container security** - Isolation and resource limits
10. **Monitoring and observability** - Metrics and structured logging

The architecture prioritizes simplicity while ensuring production-grade reliability and security. Each sprint builds upon the previous one, ensuring a working system at each stage.