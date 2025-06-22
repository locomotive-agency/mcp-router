"""
Container management service for MCP Router.

This module provides container orchestration capabilities using llm-sandbox
for secure execution of MCP servers in isolated environments.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import json
import tempfile
import shutil
from pathlib import Path

from llm_sandbox import SandboxSession
import docker
from docker.errors import DockerException

from ..config.settings import Settings
from ..models.database import MCPServer, ContainerSession
from ..utils.logging import get_logger

logger = get_logger(__name__)


class RuntimeType(str, Enum):
    """Supported container runtime types."""
    PYTHON = "python"
    NODEJS = "nodejs"
    DOCKER = "docker"
    UVX = "uvx"
    NPX = "npx"


class ContainerStatus(str, Enum):
    """Container lifecycle status."""
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class RuntimeInfo:
    """Information about detected runtime."""
    type: RuntimeType
    install_command: str
    start_command: str
    base_image: str
    dockerfile_content: Optional[str] = None
    dependencies: List[str] = None
    env_requirements: List[str] = None


@dataclass
class ContainerConfig:
    """Configuration for container execution."""
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    timeout: int = 300
    network_isolation: bool = True
    read_only: bool = False
    enable_networking: bool = False
    allowed_ports: List[int] = None
    
    def __post_init__(self):
        if self.allowed_ports is None:
            self.allowed_ports = []


@dataclass
class ExecutionResult:
    """Result of code/command execution in container."""
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    artifacts: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.artifacts is None:
            self.artifacts = []


class ContainerRuntimeDetector:
    """Detects appropriate runtime from repository content."""
    
    def __init__(self):
        self.runtime_patterns = {
            RuntimeType.NODEJS: {
                "files": ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
                "extensions": [".js", ".ts", ".jsx", ".tsx"],
                "directories": ["node_modules", "src", "lib"]
            },
            RuntimeType.PYTHON: {
                "files": ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile", "poetry.lock"],
                "extensions": [".py", ".pyx", ".pyi"],
                "directories": ["src", "lib", "__pycache__"]
            },
            RuntimeType.DOCKER: {
                "files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
                "extensions": [],
                "directories": []
            }
        }
    
    async def detect_runtime(self, repo_files: List[str], file_contents: Dict[str, str] = None) -> RuntimeInfo:
        """Detect the best runtime for repository files."""
        file_contents = file_contents or {}
        scores = {runtime: 0 for runtime in RuntimeType}
        
        # Score based on file presence
        for filename in repo_files:
            file_lower = filename.lower()
            for runtime, patterns in self.runtime_patterns.items():
                # Check direct file matches
                if any(pattern in file_lower for pattern in patterns["files"]):
                    scores[runtime] += 10
                
                # Check file extensions
                if any(file_lower.endswith(ext) for ext in patterns["extensions"]):
                    scores[runtime] += 2
                
                # Check directory presence
                if any(dir_name in file_lower for dir_name in patterns["directories"]):
                    scores[runtime] += 1
        
        # Determine highest scoring runtime
        best_runtime = max(scores.items(), key=lambda x: x[1])[0]
        
        # Generate runtime-specific configuration
        return await self._generate_runtime_info(best_runtime, repo_files, file_contents)
    
    async def _generate_runtime_info(
        self, 
        runtime_type: RuntimeType, 
        repo_files: List[str], 
        file_contents: Dict[str, str]
    ) -> RuntimeInfo:
        """Generate runtime configuration for detected type."""
        
        if runtime_type == RuntimeType.NODEJS:
            return RuntimeInfo(
                type=RuntimeType.NODEJS,
                install_command="npm install",
                start_command="npm start",
                base_image="node:18-alpine",
                dependencies=self._extract_node_dependencies(file_contents.get("package.json", "")),
                env_requirements=["NODE_ENV", "PORT"]
            )
        
        elif runtime_type == RuntimeType.PYTHON:
            return RuntimeInfo(
                type=RuntimeType.PYTHON,
                install_command=self._determine_python_install_command(repo_files, file_contents),
                start_command="python main.py",
                base_image="python:3.11-slim",
                dependencies=self._extract_python_dependencies(repo_files, file_contents),
                env_requirements=["PYTHONPATH"]
            )
        
        elif runtime_type == RuntimeType.DOCKER:
            dockerfile_content = file_contents.get("Dockerfile", "")
            return RuntimeInfo(
                type=RuntimeType.DOCKER,
                install_command="docker build -t mcp-server .",
                start_command="docker run --rm -i mcp-server",
                base_image="custom",
                dockerfile_content=dockerfile_content,
                env_requirements=self._extract_dockerfile_env(dockerfile_content)
            )
        
        else:
            # Fallback to Python
            return RuntimeInfo(
                type=RuntimeType.PYTHON,
                install_command="pip install -e .",
                start_command="python -m main",
                base_image="python:3.11-slim",
                dependencies=[],
                env_requirements=[]
            )
    
    def _extract_node_dependencies(self, package_json: str) -> List[str]:
        """Extract Node.js dependencies from package.json."""
        try:
            if package_json:
                data = json.loads(package_json)
                deps = list(data.get("dependencies", {}).keys())
                dev_deps = list(data.get("devDependencies", {}).keys())
                return deps + dev_deps
        except json.JSONDecodeError:
            pass
        return []
    
    def _extract_python_dependencies(self, repo_files: List[str], file_contents: Dict[str, str]) -> List[str]:
        """Extract Python dependencies from various config files."""
        dependencies = []
        
        # Check requirements.txt
        if "requirements.txt" in file_contents:
            lines = file_contents["requirements.txt"].split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extract package name before version specifier
                    package = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
                    dependencies.append(package)
        
        # Check pyproject.toml
        if "pyproject.toml" in file_contents:
            # Basic TOML parsing for dependencies
            content = file_contents["pyproject.toml"]
            if "[tool.poetry.dependencies]" in content:
                # Poetry dependencies parsing (simplified)
                lines = content.split('\n')
                in_deps = False
                for line in lines:
                    if "[tool.poetry.dependencies]" in line:
                        in_deps = True
                    elif line.startswith('[') and in_deps:
                        break
                    elif in_deps and '=' in line:
                        package = line.split('=')[0].strip().strip('"')
                        if package != "python":
                            dependencies.append(package)
        
        return dependencies
    
    def _determine_python_install_command(self, repo_files: List[str], file_contents: Dict[str, str]) -> str:
        """Determine the best installation command for Python project."""
        if "pyproject.toml" in repo_files:
            content = file_contents.get("pyproject.toml", "")
            if "tool.poetry" in content:
                return "poetry install"
            else:
                return "pip install -e ."
        elif "requirements.txt" in repo_files:
            return "pip install -r requirements.txt"
        elif "setup.py" in repo_files:
            return "pip install -e ."
        else:
            return "pip install ."
    
    def _extract_dockerfile_env(self, dockerfile_content: str) -> List[str]:
        """Extract environment variables from Dockerfile."""
        env_vars = []
        for line in dockerfile_content.split('\n'):
            line = line.strip()
            if line.startswith('ENV '):
                # Extract ENV variable names
                env_part = line[4:].strip()
                if '=' in env_part:
                    var_name = env_part.split('=')[0].strip()
                    env_vars.append(var_name)
        return env_vars


class ContainerManager:
    """Manages container lifecycle using llm-sandbox."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.detector = ContainerRuntimeDetector()
        self.active_sessions: Dict[str, SandboxSession] = {}
        self.session_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Default container configuration
        self.default_config = ContainerConfig(
            memory_limit=settings.container_memory_limit,
            cpu_limit=settings.container_cpu_limit,
            timeout=settings.container_timeout,
            network_isolation=True,
            read_only=False,
            enable_networking=True,  # MCP servers may need network access
            allowed_ports=[8080, 3000, 5000]  # Common ports for MCP servers
        )
        
        logger.info("Container manager initialized", extra={
            "backend": settings.container_backend,
            "max_containers": settings.max_concurrent_containers
        })
    
    async def detect_runtime(self, repo_files: List[str], file_contents: Dict[str, str] = None) -> RuntimeInfo:
        """Detect runtime for repository."""
        return await self.detector.detect_runtime(repo_files, file_contents)
    
    async def create_session(
        self, 
        server: MCPServer, 
        config: Optional[ContainerConfig] = None
    ) -> str:
        """Create a new container session for MCP server."""
        
        session_id = f"{server.id}_{int(time.time())}"
        container_config = config or self.default_config
        
        try:
            # Determine sandbox configuration based on runtime
            sandbox_config = await self._prepare_sandbox_config(server, container_config)
            
            # Create sandbox session
            session = SandboxSession(**sandbox_config)
            
            # Store session
            self.active_sessions[session_id] = session
            self.session_metadata[session_id] = {
                "server_id": server.id,
                "created_at": time.time(),
                "status": ContainerStatus.PENDING,
                "config": container_config
            }
            
            logger.info("Container session created", extra={
                "session_id": session_id,
                "server_id": server.id,
                "runtime_type": server.runtime_type
            })
            
            return session_id
            
        except Exception as e:
            logger.error("Failed to create container session", extra={
                "server_id": server.id,
                "error": str(e)
            })
            raise
    
    async def start_session(self, session_id: str) -> bool:
        """Start a container session."""
        if session_id not in self.active_sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.active_sessions[session_id]
        metadata = self.session_metadata[session_id]
        
        try:
            metadata["status"] = ContainerStatus.STARTING
            
            # Open the sandbox session
            await asyncio.get_event_loop().run_in_executor(None, session.open)
            
            metadata["status"] = ContainerStatus.RUNNING
            metadata["started_at"] = time.time()
            
            logger.info("Container session started", extra={
                "session_id": session_id,
                "server_id": metadata["server_id"]
            })
            
            return True
            
        except Exception as e:
            metadata["status"] = ContainerStatus.ERROR
            logger.error("Failed to start container session", extra={
                "session_id": session_id,
                "error": str(e)
            })
            return False
    
    async def execute_command(
        self, 
        session_id: str, 
        command: str, 
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """Execute a command in the container session."""
        if session_id not in self.active_sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.active_sessions[session_id]
        metadata = self.session_metadata[session_id]
        
        if metadata["status"] != ContainerStatus.RUNNING:
            raise RuntimeError(f"Session {session_id} is not running")
        
        try:
            start_time = time.time()
            
            # Execute command in sandbox
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.run(command)
            )
            
            execution_time = time.time() - start_time
            
            # Extract artifacts if any
            artifacts = []
            try:
                sandbox_artifacts = session.get_artifacts()
                for artifact in sandbox_artifacts:
                    artifacts.append({
                        "type": "file",
                        "name": artifact.get("filename", "unknown"),
                        "content": artifact.get("data", ""),
                        "encoding": "base64"
                    })
            except Exception as e:
                logger.warning("Failed to extract artifacts", extra={
                    "session_id": session_id,
                    "error": str(e)
                })
            
            return ExecutionResult(
                stdout=getattr(result, 'stdout', str(result)),
                stderr=getattr(result, 'stderr', ''),
                exit_code=getattr(result, 'exit_code', 0),
                execution_time=execution_time,
                artifacts=artifacts
            )
            
        except Exception as e:
            logger.error("Command execution failed", extra={
                "session_id": session_id,
                "command": command[:100],  # Truncate for logging
                "error": str(e)
            })
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                execution_time=0.0
            )
    
    async def install_dependencies(
        self, 
        session_id: str, 
        dependencies: List[str],
        runtime_type: RuntimeType = RuntimeType.PYTHON
    ) -> ExecutionResult:
        """Install dependencies in the container session."""
        if runtime_type == RuntimeType.PYTHON:
            command = f"pip install {' '.join(dependencies)}"
        elif runtime_type == RuntimeType.NODEJS:
            command = f"npm install {' '.join(dependencies)}"
        else:
            raise ValueError(f"Dependency installation not supported for {runtime_type}")
        
        return await self.execute_command(session_id, command)
    
    async def copy_to_session(self, session_id: str, local_path: str, remote_path: str) -> bool:
        """Copy file from host to container session."""
        if session_id not in self.active_sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.active_sessions[session_id]
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.copy_to_runtime(local_path, remote_path)
            )
            return True
        except Exception as e:
            logger.error("Failed to copy file to session", extra={
                "session_id": session_id,
                "local_path": local_path,
                "remote_path": remote_path,
                "error": str(e)
            })
            return False
    
    async def copy_from_session(self, session_id: str, remote_path: str, local_path: str) -> bool:
        """Copy file from container session to host."""
        if session_id not in self.active_sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.active_sessions[session_id]
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.copy_from_runtime(remote_path, local_path)
            )
            return True
        except Exception as e:
            logger.error("Failed to copy file from session", extra={
                "session_id": session_id,
                "remote_path": remote_path,
                "local_path": local_path,
                "error": str(e)
            })
            return False
    
    async def stop_session(self, session_id: str) -> bool:
        """Stop and cleanup a container session."""
        if session_id not in self.active_sessions:
            return True  # Already stopped
        
        session = self.active_sessions[session_id]
        metadata = self.session_metadata[session_id]
        
        try:
            metadata["status"] = ContainerStatus.STOPPING
            
            # Close the sandbox session
            await asyncio.get_event_loop().run_in_executor(None, session.close)
            
            metadata["status"] = ContainerStatus.STOPPED
            metadata["stopped_at"] = time.time()
            
            # Remove from active sessions
            del self.active_sessions[session_id]
            
            logger.info("Container session stopped", extra={
                "session_id": session_id,
                "server_id": metadata["server_id"]
            })
            
            return True
            
        except Exception as e:
            metadata["status"] = ContainerStatus.ERROR
            logger.error("Failed to stop container session", extra={
                "session_id": session_id,
                "error": str(e)
            })
            return False
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active container sessions."""
        sessions = []
        for session_id, metadata in self.session_metadata.items():
            sessions.append({
                "session_id": session_id,
                "server_id": metadata["server_id"],
                "status": metadata["status"],
                "created_at": metadata["created_at"],
                "started_at": metadata.get("started_at"),
                "stopped_at": metadata.get("stopped_at")
            })
        return sessions
    
    async def get_session_status(self, session_id: str) -> Optional[ContainerStatus]:
        """Get status of a container session."""
        metadata = self.session_metadata.get(session_id)
        return metadata["status"] if metadata else None
    
    async def cleanup_all_sessions(self) -> int:
        """Stop and cleanup all active sessions."""
        cleanup_count = 0
        session_ids = list(self.active_sessions.keys())
        
        for session_id in session_ids:
            if await self.stop_session(session_id):
                cleanup_count += 1
        
        logger.info("Cleaned up container sessions", extra={
            "count": cleanup_count
        })
        
        return cleanup_count
    
    async def _prepare_sandbox_config(
        self, 
        server: MCPServer, 
        container_config: ContainerConfig
    ) -> Dict[str, Any]:
        """Prepare configuration for llm-sandbox session."""
        
        # Base configuration
        config = {
            "verbose": self.settings.debug,
            "keep_template": True,  # Reuse images for efficiency
        }
        
        # Runtime-specific configuration
        if server.runtime_type == "python" or server.runtime_type == "uvx":
            config.update({
                "lang": "python",
                "image": "python:3.11-slim"
            })
        elif server.runtime_type == "nodejs" or server.runtime_type == "npx":
            config.update({
                "lang": "javascript",
                "image": "node:18-alpine"
            })
        elif server.runtime_type == "docker":
            # For custom Docker images, we'll use a custom Dockerfile
            config.update({
                "lang": "python",  # Default fallback
                "image": "python:3.11-slim"
            })
        
        # Add environment variables
        env_vars = {}
        for env_var in server.env_variables:
            env_vars[env_var.key] = env_var.value or ""
        
        if env_vars:
            config["env_vars"] = env_vars
        
        return config 