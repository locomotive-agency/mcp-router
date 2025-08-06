"""Configuration routes for Claude Desktop integration.

This module provides endpoints to generate and serve configuration files
needed to integrate MCP Anywhere with Claude Desktop when running in STDIO mode.
"""

import json
import sys
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


def generate_claude_config() -> dict[str, Any]:
    """Generate Claude Desktop configuration for MCP Anywhere.

    Returns:
        Dict containing the Claude Desktop configuration structure
    """
    # Determine Python executable path
    python_cmd = sys.executable if sys.executable else "python3"

    config = {
        "mcpServers": {
            "mcp-anywhere": {
                "command": python_cmd,
                "args": ["-m", "mcp_anywhere", "connect"],
                "env": {
                    # Add any required environment variables here
                    "PYTHONUNBUFFERED": "1"
                },
            }
        }
    }

    return config


async def config_download(request: Request) -> Response:
    """Endpoint to download Claude Desktop configuration file.

    Args:
        request: The incoming HTTP request

    Returns:
        JSON response with configuration file as download
    """
    # Check transport mode
    transport_mode = getattr(request.app.state, "transport_mode", "http")

    if transport_mode != "stdio":
        # In HTTP mode, return a different configuration or message
        return JSONResponse(
            {
                "error": "Configuration download is only available in STDIO mode",
                "message": "HTTP mode uses direct API endpoints and doesn't require Claude Desktop configuration",
            },
            status_code=400,
        )

    # Generate configuration
    config = generate_claude_config()

    # Convert to JSON string with nice formatting
    config_json = json.dumps(config, indent=2)

    # Return as downloadable JSON file
    return Response(
        content=config_json,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=claude_desktop_config.json"},
    )


async def config_view(request: Request) -> JSONResponse:
    """Endpoint to view Claude Desktop configuration as JSON.

    Args:
        request: The incoming HTTP request

    Returns:
        JSON response with configuration
    """
    # Check transport mode
    transport_mode = getattr(request.app.state, "transport_mode", "http")

    if transport_mode != "stdio":
        return JSONResponse(
            {
                "error": "Configuration view is only available in STDIO mode",
                "transport_mode": transport_mode,
            },
            status_code=400,
        )

    # Generate and return configuration
    config = generate_claude_config()
    return JSONResponse(config)


async def config_instructions(request: Request) -> HTMLResponse:
    """Endpoint to show setup instructions for Claude Desktop integration.

    Args:
        request: The incoming HTTP request

    Returns:
        HTML response with setup instructions
    """
    transport_mode = getattr(request.app.state, "transport_mode", "http")

    if transport_mode != "stdio":
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>MCP Anywhere - HTTP Mode</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-50 p-8">
            <div class="max-w-4xl mx-auto">
                <div class="bg-white rounded-lg shadow-md p-6">
                    <h1 class="text-2xl font-bold mb-4">HTTP Mode Active</h1>
                    <p class="text-gray-700 mb-4">
                        MCP Anywhere is running in HTTP mode. Claude Desktop configuration 
                        is not needed for HTTP mode as it uses direct API endpoints.
                    </p>
                    <a href="/" class="text-blue-600 hover:underline">← Back to Dashboard</a>
                </div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(html_content)

    # Get Python command used
    python_cmd = sys.executable if sys.executable else "python3"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Claude Desktop Setup - MCP Anywhere</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50 p-8">
        <div class="max-w-4xl mx-auto">
            <div class="bg-white rounded-lg shadow-md p-6">
                <h1 class="text-2xl font-bold mb-6">Claude Desktop Integration Setup</h1>
                
                <div class="space-y-6">
                    <section>
                        <h2 class="text-lg font-semibold mb-3">Step 1: Download Configuration</h2>
                        <p class="text-gray-700 mb-3">
                            Download the configuration file for Claude Desktop:
                        </p>
                        <a href="/config/download" 
                           class="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                                      d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
                                </path>
                            </svg>
                            Download claude_desktop_config.json
                        </a>
                    </section>
                    
                    <section>
                        <h2 class="text-lg font-semibold mb-3">Step 2: Locate Claude Desktop Config Directory</h2>
                        <p class="text-gray-700 mb-3">
                            Find your Claude Desktop configuration directory based on your operating system:
                        </p>
                        <div class="bg-gray-100 rounded p-4 space-y-2">
                            <div>
                                <strong>macOS:</strong> 
                                <code class="bg-gray-200 px-2 py-1 rounded text-sm">~/Library/Application Support/Claude/</code>
                            </div>
                            <div>
                                <strong>Windows:</strong> 
                                <code class="bg-gray-200 px-2 py-1 rounded text-sm">%APPDATA%\\Claude\\</code>
                            </div>
                            <div>
                                <strong>Linux:</strong> 
                                <code class="bg-gray-200 px-2 py-1 rounded text-sm">~/.config/claude/</code>
                            </div>
                        </div>
                    </section>
                    
                    <section>
                        <h2 class="text-lg font-semibold mb-3">Step 3: Install Configuration</h2>
                        <p class="text-gray-700 mb-3">
                            Place the downloaded <code class="bg-gray-200 px-2 py-1 rounded">claude_desktop_config.json</code> 
                            file in the configuration directory.
                        </p>
                        <div class="bg-yellow-50 border border-yellow-200 rounded p-4">
                            <p class="text-yellow-800 text-sm">
                                <strong>Note:</strong> If you already have a configuration file, you'll need to merge 
                                the MCP Anywhere server configuration into your existing file.
                            </p>
                        </div>
                    </section>
                    
                    <section>
                        <h2 class="text-lg font-semibold mb-3">Step 4: Verify Installation</h2>
                        <p class="text-gray-700 mb-3">
                            The configuration will add MCP Anywhere to Claude Desktop with this command:
                        </p>
                        <div class="bg-gray-100 rounded p-4">
                            <code class="text-sm">{python_cmd} -m mcp_anywhere connect</code>
                        </div>
                        <p class="text-gray-700 mt-3">
                            Restart Claude Desktop after installing the configuration file.
                        </p>
                    </section>
                    
                    <section>
                        <h2 class="text-lg font-semibold mb-3">Configuration Preview</h2>
                        <p class="text-gray-700 mb-3">
                            View the configuration that will be downloaded:
                        </p>
                        <a href="/config/view" target="_blank"
                           class="inline-flex items-center px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700">
                            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                                      d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z">
                                </path>
                            </svg>
                            View Configuration JSON
                        </a>
                    </section>
                </div>
                
                <div class="mt-8 pt-6 border-t">
                    <a href="/" class="text-blue-600 hover:underline">← Back to Dashboard</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(html_content)


# Define routes for configuration endpoints
config_routes = [
    Route("/config/download", config_download, methods=["GET"]),
    Route("/config/view", config_view, methods=["GET"]),
    Route("/config/instructions", config_instructions, methods=["GET"]),
]
