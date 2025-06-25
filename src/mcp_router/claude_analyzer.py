"""Analyzes GitHub repositories to extract MCP server configuration using Claude"""
import os
import re
import base64
import httpx
from anthropic import Anthropic, AnthropicError
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ClaudeAnalyzer:
    """Analyzes GitHub repositories to extract MCP server configuration"""

    def __init__(self, api_key: Optional[str] = None, github_token: Optional[str] = None):
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for ClaudeAnalyzer")
        self.client = Anthropic(api_key=self.api_key)
        self.github_token = github_token or os.environ.get('GITHUB_TOKEN')
        self.model_name = os.environ.get('ANTHROPIC_MODEL_NAME', "claude-sonnet-4-20250514")

    def analyze_repository(self, github_url: str) -> Dict[str, Any]:
        """
        Analyze a GitHub repository and return a structured configuration.

        Args:
            github_url: The URL of the GitHub repository.

        Returns:
            A dictionary containing the extracted server configuration.
        """
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)', github_url)
        if not match:
            raise ValueError("Invalid GitHub URL format. Expected: https://github.com/owner/repo")
        
        owner, repo = match.groups()

        try:
            readme = self._fetch_file(owner, repo, 'README.md')
            package_json = self._fetch_file(owner, repo, 'package.json')
            pyproject = self._fetch_file(owner, repo, 'pyproject.toml')
        except httpx.HTTPStatusError as e:
            logger.error(f"GitHub API error: {e}")
            raise ConnectionError(f"Failed to fetch files from GitHub: {e.response.status_code}")

        prompt = self._build_prompt(github_url, readme, package_json, pyproject)

        try:
            message = self.client.messages.create(
                model=self.model_name,
                max_tokens=1024,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}]
            )
            analysis_text = message.content[0].text
            return self._parse_claude_response(analysis_text)
        except AnthropicError as e:
            logger.error(f"Claude API error: {e}")
            raise ConnectionError(f"Failed to get analysis from Claude: {e}")

    def _fetch_file(self, owner: str, repo: str, path: str) -> Optional[str]:
        """Fetch file content from a public GitHub repository."""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {'Accept': 'application/vnd.github.v3+json'}
        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'
        
        try:
            with httpx.Client() as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                content = response.json()['content']
                return base64.b64decode(content).decode('utf-8')
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None  # File not found is not an error
            raise
        except Exception as e:
            logger.warning(f"Could not fetch {path} from {owner}/{repo}: {e}")
            return None

    def _build_prompt(self, url: str, readme: Optional[str], pkg_json: Optional[str], pyproject: Optional[str]) -> str:
        """Constructs the prompt for the Claude API call."""
        return f"""
Analyze the following MCP server repository to determine its configuration.

Repository URL: {url}

Here are the contents of key files:

<file path="README.md">
{readme or "Not found."}
</file>

<file path="package.json">
{pkg_json or "Not found."}
</file>

<file path="pyproject.toml">
{pyproject or "Not found."}
</file>

Based on the file contents, extract the following information. Be precise and concise.

1.  **Runtime type**: Determine if this is 'npx' (for Node.js), 'uvx' (for Python), or 'docker'. Prioritize `pyproject.toml` for Python projects and `package.json` for Node.js projects.
2.  **Install command**: The command to install dependencies (e.g., "npm install" or "pip install -e ."). If not needed, respond with "none".
3.  **Start command**: The command to run the server (e.g., "npx mcp-server" or "python -m mcp_server"). This is the most critical piece of information.
4.  **Server name**: A short, descriptive, machine-readable name for the server (e.g., "financial-data-api").
5.  **Description**: A brief, one-sentence description of the server's purpose.
6.  **Environment Variables**: List any required environment variables, their purpose, and if they are required.

Respond in this exact, parsable format. Do not add any conversational text or pleasantries.

RUNTIME: [npx|uvx|docker]
INSTALL: [command or "none"]
START: [command]
NAME: [server name]
DESCRIPTION: [one-line description]
ENV_VARS:
- KEY: [key name], DESC: [description], REQUIRED: [true|false]
- KEY: [key name], DESC: [description], REQUIRED: [true|false]
"""

    def _parse_claude_response(self, text: str) -> Dict[str, Any]:
        """Parse Claude's structured response into a dictionary."""
        result = {
            'runtime_type': 'docker',
            'install_command': '',
            'start_command': '',
            'name': 'unnamed-server',
            'description': '',
            'env_variables': []
        }
        
        for line in text.splitlines():
            if line.startswith('RUNTIME:'):
                result['runtime_type'] = line.split(':', 1)[1].strip()
            elif line.startswith('INSTALL:'):
                cmd = line.split(':', 1)[1].strip()
                result['install_command'] = cmd if cmd.lower() != 'none' else ''
            elif line.startswith('START:'):
                result['start_command'] = line.split(':', 1)[1].strip()
            elif line.startswith('NAME:'):
                result['name'] = line.split(':', 1)[1].strip()
            elif line.startswith('DESCRIPTION:'):
                result['description'] = line.split(':', 1)[1].strip()
            elif line.startswith('- KEY:'):
                try:
                    parts = [p.strip() for p in line.split(',')]
                    key = parts[0].split(':', 1)[1].strip()
                    desc = parts[1].split(':', 1)[1].strip() if len(parts) > 1 else ''
                    req_str = parts[2].split(':', 1)[1].strip() if len(parts) > 2 else 'true'
                    required = req_str.lower() == 'true'
                    result['env_variables'].append({'key': key, 'description': desc, 'required': required})
                except IndexError:
                    logger.warning(f"Could not parse env var line: {line}")

        return result 