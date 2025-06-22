"""
GitHub integration service for MCP Router.

This module provides functionality to analyze GitHub repositories
and extract information needed for MCP server configuration.
"""

import asyncio
import base64
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from dataclasses import dataclass

import httpx
from github import Github, Repository
from github.GithubException import GithubException

from ..config.settings import Settings
from ..utils.logging import get_logger
from .container_manager import RuntimeInfo, ContainerRuntimeDetector

logger = get_logger(__name__)


@dataclass
class RepoInfo:
    """Repository information."""
    owner: str
    name: str
    full_name: str
    description: str
    default_branch: str
    clone_url: str
    ssh_url: str
    stars: int
    language: Optional[str]
    topics: List[str]


@dataclass
class RepoContent:
    """Repository content and files."""
    files: List[str]
    file_contents: Dict[str, str]
    readme_content: str
    package_files: Dict[str, str]
    directory_structure: List[str]


class GitHubService:
    """Service for GitHub repository analysis."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.github_client = None
        self.http_client = httpx.AsyncClient()
        self.runtime_detector = ContainerRuntimeDetector()
        
        # Initialize GitHub client if token is available
        if settings.github_token:
            self.github_client = Github(settings.github_token)
            logger.info("GitHub client initialized with authentication")
        else:
            self.github_client = Github()
            logger.warning("GitHub client initialized without authentication (rate limited)")
    
    async def parse_github_url(self, github_url: str) -> Tuple[str, str]:
        """Parse GitHub URL to extract owner and repository name."""
        # Remove trailing .git if present
        url = github_url.rstrip('.git')
        
        # Parse the URL
        parsed = urlparse(url)
        
        if parsed.netloc != 'github.com':
            raise ValueError(f"Not a GitHub URL: {github_url}")
        
        # Extract owner and repo from path
        path_parts = parsed.path.strip('/').split('/')
        
        if len(path_parts) < 2:
            raise ValueError(f"Invalid GitHub repository URL: {github_url}")
        
        owner = path_parts[0]
        repo = path_parts[1]
        
        return owner, repo
    
    async def get_repository_info(self, github_url: str) -> RepoInfo:
        """Get basic repository information."""
        owner, repo_name = await self.parse_github_url(github_url)
        
        try:
            repo = self.github_client.get_repo(f"{owner}/{repo_name}")
            
            return RepoInfo(
                owner=owner,
                name=repo_name,
                full_name=repo.full_name,
                description=repo.description or "",
                default_branch=repo.default_branch,
                clone_url=repo.clone_url,
                ssh_url=repo.ssh_url,
                stars=repo.stargazers_count,
                language=repo.language,
                topics=repo.get_topics()
            )
            
        except GithubException as e:
            logger.error("Failed to fetch repository info", extra={
                "github_url": github_url,
                "error": str(e)
            })
            raise ValueError(f"Failed to access repository: {e}")
    
    async def fetch_repository_content(self, github_url: str, max_files: int = 50) -> RepoContent:
        """Fetch repository content for analysis."""
        owner, repo_name = await self.parse_github_url(github_url)
        
        try:
            repo = self.github_client.get_repo(f"{owner}/{repo_name}")
            
            # Get repository contents
            files = []
            file_contents = {}
            package_files = {}
            directory_structure = []
            readme_content = ""
            
            # Fetch root directory contents
            contents = repo.get_contents("")
            
            # Process files in root and important subdirectories
            await self._process_contents(
                repo, contents, files, file_contents, package_files, 
                directory_structure, max_files
            )
            
            # Try to get README content
            readme_content = await self._get_readme_content(repo)
            
            return RepoContent(
                files=files,
                file_contents=file_contents,
                readme_content=readme_content,
                package_files=package_files,
                directory_structure=directory_structure
            )
            
        except GithubException as e:
            logger.error("Failed to fetch repository content", extra={
                "github_url": github_url,
                "error": str(e)
            })
            raise ValueError(f"Failed to fetch repository content: {e}")
    
    async def _process_contents(
        self,
        repo: Repository,
        contents,
        files: List[str],
        file_contents: Dict[str, str],
        package_files: Dict[str, str],
        directory_structure: List[str],
        max_files: int,
        current_path: str = ""
    ):
        """Process repository contents recursively."""
        important_files = {
            "package.json", "package-lock.json", "yarn.lock",
            "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            "README.md", "README.rst", "README.txt", "README",
            ".gitignore", "LICENSE", "Makefile"
        }
        
        important_directories = {
            "src", "lib", "app", "server", "client", "public", "static",
            "tests", "test", "__tests__", "spec", "examples", "docs"
        }
        
        for content in contents:
            if len(files) >= max_files:
                break
            
            file_path = f"{current_path}/{content.name}" if current_path else content.name
            
            if content.type == "dir":
                directory_structure.append(file_path)
                
                # Recursively process important directories (limited depth)
                if (content.name in important_directories and 
                    current_path.count('/') < 2):  # Limit recursion depth
                    try:
                        subcontents = repo.get_contents(content.path)
                        await self._process_contents(
                            repo, subcontents, files, file_contents, 
                            package_files, directory_structure, max_files, file_path
                        )
                    except GithubException:
                        pass  # Skip if can't access subdirectory
            
            elif content.type == "file":
                files.append(file_path)
                
                # Download content for important files
                if (content.name in important_files or 
                    file_path.endswith(('.py', '.js', '.ts', '.json', '.yml', '.yaml', '.toml', '.md'))):
                    
                    try:
                        file_content = await self._get_file_content(repo, content.path)
                        file_contents[file_path] = file_content
                        
                        # Store package files separately
                        if content.name in important_files:
                            package_files[content.name] = file_content
                            
                    except Exception as e:
                        logger.warning("Failed to fetch file content", extra={
                            "file_path": file_path,
                            "error": str(e)
                        })
    
    async def _get_file_content(self, repo: Repository, file_path: str) -> str:
        """Get content of a specific file."""
        try:
            file_content = repo.get_contents(file_path)
            
            if file_content.encoding == "base64":
                content = base64.b64decode(file_content.content).decode('utf-8')
            else:
                content = file_content.content
            
            return content
            
        except UnicodeDecodeError:
            # If it's a binary file, return empty string
            return ""
        except GithubException as e:
            logger.warning("Failed to get file content", extra={
                "file_path": file_path,
                "error": str(e)
            })
            return ""
    
    async def _get_readme_content(self, repo: Repository) -> str:
        """Get README file content."""
        readme_names = ["README.md", "README.rst", "README.txt", "README", "readme.md"]
        
        for readme_name in readme_names:
            try:
                readme = repo.get_contents(readme_name)
                if readme.encoding == "base64":
                    return base64.b64decode(readme.content).decode('utf-8')
                else:
                    return readme.content
            except GithubException:
                continue
        
        return ""
    
    async def analyze_repository(self, github_url: str) -> Dict[str, any]:
        """Analyze repository and generate MCP server configuration."""
        try:
            # Get repository info and content
            repo_info = await self.get_repository_info(github_url)
            repo_content = await self.fetch_repository_content(github_url)
            
            # Detect runtime
            runtime_info = await self.runtime_detector.detect_runtime(
                repo_content.files, 
                repo_content.file_contents
            )
            
            # Extract MCP-specific information
            mcp_info = await self._analyze_mcp_capabilities(repo_content)
            
            # Generate server configuration
            config = {
                "name": self._generate_server_name(repo_info.name),
                "display_name": repo_info.name.replace('-', ' ').replace('_', ' ').title(),
                "description": repo_info.description or f"MCP server from {repo_info.full_name}",
                "github_url": github_url,
                "runtime_type": runtime_info.type.value,
                "install_command": runtime_info.install_command,
                "start_command": await self._determine_start_command(runtime_info, repo_content),
                "transport_type": await self._detect_transport_type(repo_content),
                "transport_config": {},
                "env_variables": await self._extract_env_variables(repo_content, runtime_info),
                "capabilities": mcp_info,
                "detected_tools": await self._detect_available_tools(repo_content),
                "repository_info": {
                    "owner": repo_info.owner,
                    "stars": repo_info.stars,
                    "language": repo_info.language,
                    "topics": repo_info.topics
                }
            }
            
            logger.info("Repository analysis completed", extra={
                "github_url": github_url,
                "runtime_type": runtime_info.type.value,
                "transport_type": config["transport_type"]
            })
            
            return config
            
        except Exception as e:
            logger.error("Repository analysis failed", extra={
                "github_url": github_url,
                "error": str(e)
            })
            raise
    
    def _generate_server_name(self, repo_name: str) -> str:
        """Generate a valid server name from repository name."""
        # Convert to lowercase and replace invalid characters
        name = re.sub(r'[^a-z0-9\-_]', '-', repo_name.lower())
        # Remove consecutive dashes
        name = re.sub(r'-+', '-', name)
        # Remove leading/trailing dashes
        name = name.strip('-')
        
        return name or "mcp-server"
    
    async def _analyze_mcp_capabilities(self, repo_content: RepoContent) -> Dict[str, any]:
        """Analyze repository for MCP-specific capabilities."""
        capabilities = {
            "tools": [],
            "resources": [],
            "prompts": [],
            "sampling": False
        }
        
        # Look for MCP-related files and patterns
        mcp_keywords = ["mcp", "model-context-protocol", "fastmcp", "tool", "resource", "prompt"]
        
        # Check README and other documentation
        readme_lower = repo_content.readme_content.lower()
        for keyword in mcp_keywords:
            if keyword in readme_lower:
                capabilities["mcp_references"] = True
                break
        
        # Check for tool definitions in code files
        for file_path, content in repo_content.file_contents.items():
            if file_path.endswith(('.py', '.js', '.ts')):
                content_lower = content.lower()
                
                # Look for tool patterns
                if any(pattern in content_lower for pattern in ["@tool", "def tool_", "function tool", "mcp.tool"]):
                    capabilities["tools"].append(f"Tool found in {file_path}")
                
                # Look for resource patterns
                if any(pattern in content_lower for pattern in ["@resource", "def resource_", "mcp.resource"]):
                    capabilities["resources"].append(f"Resource found in {file_path}")
                
                # Look for prompt patterns
                if any(pattern in content_lower for pattern in ["@prompt", "def prompt_", "mcp.prompt"]):
                    capabilities["prompts"].append(f"Prompt found in {file_path}")
        
        return capabilities
    
    async def _determine_start_command(self, runtime_info: RuntimeInfo, repo_content: RepoContent) -> str:
        """Determine the best start command for the MCP server."""
        # Check for MCP-specific start patterns
        
        # Look in package.json for npm scripts
        if "package.json" in repo_content.package_files:
            try:
                import json
                package_data = json.loads(repo_content.package_files["package.json"])
                scripts = package_data.get("scripts", {})
                
                # Look for MCP-specific scripts
                if "mcp" in scripts:
                    return "npm run mcp"
                elif "start:mcp" in scripts:
                    return "npm run start:mcp"
                elif "server" in scripts:
                    return "npm run server"
                elif "start" in scripts:
                    return "npm start"
            except json.JSONDecodeError:
                pass
        
        # Look for main entry points
        common_entry_points = [
            "main.py", "server.py", "app.py", "index.py",
            "main.js", "server.js", "app.js", "index.js",
            "src/main.py", "src/server.py", "src/app.py",
            "src/main.js", "src/server.js", "src/app.js"
        ]
        
        for entry_point in common_entry_points:
            if entry_point in repo_content.files:
                if runtime_info.type.value == "python":
                    return f"python {entry_point}"
                elif runtime_info.type.value == "nodejs":
                    return f"node {entry_point}"
        
        # Fallback to runtime default
        return runtime_info.start_command
    
    async def _detect_transport_type(self, repo_content: RepoContent) -> str:
        """Detect the transport type used by the MCP server."""
        # Default to stdio for MCP servers
        transport_type = "stdio"
        
        # Look for HTTP/SSE indicators in code
        for file_path, content in repo_content.file_contents.items():
            content_lower = content.lower()
            
            # Look for HTTP server patterns
            if any(pattern in content_lower for pattern in [
                "fastapi", "flask", "express", "http.server", "app.listen",
                "httpx", "requests", "axios", "fetch"
            ]):
                transport_type = "http"
                break
            
            # Look for SSE patterns
            if any(pattern in content_lower for pattern in [
                "server-sent", "eventsource", "sse", "text/event-stream"
            ]):
                transport_type = "sse"
                break
        
        return transport_type
    
    async def _extract_env_variables(self, repo_content: RepoContent, runtime_info: RuntimeInfo) -> List[Dict[str, any]]:
        """Extract required environment variables from repository."""
        env_vars = []
        found_vars = set()
        
        # Common environment variable patterns
        env_patterns = [
            r'(?:os\.environ|process\.env)\[[\'"](.*?)[\'"]\]',
            r'(?:os\.getenv|getenv)\([\'"](.*?)[\'"]\)',
            r'(?:ENV|env)\s+([A-Z_][A-Z0-9_]*)',
            r'([A-Z_][A-Z0-9_]*)\s*=.*?(?:env|ENV)',
        ]
        
        # Look through all files for environment variable usage
        for file_path, content in repo_content.file_contents.items():
            for pattern in env_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    var_name = match.upper().strip()
                    if var_name and var_name not in found_vars:
                        found_vars.add(var_name)
                        
                        # Determine if it's likely a secret
                        is_secret = any(keyword in var_name.lower() for keyword in [
                            'key', 'secret', 'token', 'password', 'pwd', 'auth', 'api'
                        ])
                        
                        env_vars.append({
                            "key": var_name,
                            "description": self._generate_env_description(var_name),
                            "is_required": True,
                            "is_secret": is_secret,
                            "default_value": None
                        })
        
        # Add runtime-specific requirements
        if runtime_info.env_requirements:
            for env_var in runtime_info.env_requirements:
                if env_var not in found_vars:
                    env_vars.append({
                        "key": env_var,
                        "description": f"Runtime requirement for {runtime_info.type.value}",
                        "is_required": False,
                        "is_secret": False,
                        "default_value": None
                    })
        
        return env_vars
    
    def _generate_env_description(self, var_name: str) -> str:
        """Generate a description for an environment variable."""
        var_lower = var_name.lower()
        
        if 'api_key' in var_lower or 'apikey' in var_lower:
            return f"API key for {var_name.replace('_', ' ').replace('API', '').replace('KEY', '').strip()}"
        elif 'token' in var_lower:
            return f"Authentication token for {var_name.replace('_', ' ').replace('TOKEN', '').strip()}"
        elif 'secret' in var_lower:
            return f"Secret key for {var_name.replace('_', ' ').replace('SECRET', '').strip()}"
        elif 'url' in var_lower:
            return f"URL endpoint for {var_name.replace('_', ' ').replace('URL', '').strip()}"
        elif 'port' in var_lower:
            return f"Port number for {var_name.replace('_', ' ').replace('PORT', '').strip()}"
        elif 'host' in var_lower:
            return f"Host address for {var_name.replace('_', ' ').replace('HOST', '').strip()}"
        else:
            return f"Configuration value for {var_name.replace('_', ' ').strip()}"
    
    async def _detect_available_tools(self, repo_content: RepoContent) -> List[str]:
        """Detect available tools/functions in the MCP server."""
        tools = []
        
        # Look for function definitions that might be tools
        function_patterns = [
            r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',  # Python functions
            r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',  # JavaScript functions
            r'async\s+function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',  # Async JS functions
            r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*async\s*\(',  # TypeScript async methods
        ]
        
        for file_path, content in repo_content.file_contents.items():
            if file_path.endswith(('.py', '.js', '.ts')):
                for pattern in function_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if not match.startswith('_'):  # Skip private functions
                            tools.append(match)
        
        # Remove duplicates and common non-tool functions
        excluded_functions = {
            'main', 'init', 'setup', 'start', 'stop', 'run', 'execute',
            'constructor', 'toString', 'valueOf', 'hasOwnProperty'
        }
        
        unique_tools = list(set(tools) - excluded_functions)
        return unique_tools[:10]  # Limit to first 10 tools
    
    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose() 