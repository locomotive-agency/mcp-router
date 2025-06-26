#!/usr/bin/env python
"""
Test script for MCP Router HTTP transport functionality.

This module provides integration tests for the HTTP transport mode of MCP Router.
It can be run standalone or as part of the test suite.

Usage:
    python tests/test_http_client.py
    
    Or with custom configuration:
    MCP_HOST=192.168.1.100 MCP_PORT=9000 python tests/test_http_client.py
"""
import asyncio
from fastmcp import Client
import os

async def test_http_connection():
    """Test connecting to MCP Router via HTTP transport"""
    # Get configuration from environment
    host = os.environ.get('MCP_HOST', '127.0.0.1')
    port = os.environ.get('MCP_PORT', '8001')
    path = os.environ.get('MCP_PATH', '/mcp')
    api_key = os.environ.get('MCP_API_KEY')
    
    url = f"http://{host}:{port}{path}"
    
    print(f"Connecting to MCP Router at {url}")
    if api_key:
        print("Using API key authentication")
    else:
        print("Warning: No API key set - connection may fail if server requires authentication")
    
    try:
        # In FastMCP 2.x, authentication for clients is handled differently
        # For HTTP transports, we can pass auth tokens via the auth parameter
        auth = None
        if api_key:
            # Use Bearer token authentication for HTTP transport
            from fastmcp.client.auth import BearerAuth
            auth = BearerAuth(token=api_key)
        
        async with Client(url, auth=auth) as client:
            print("✓ Connected successfully!")
            
            # List available tools
            print("\nAvailable tools:")
            tools = await client.list_tools()
            for tool in tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # Test list_providers
            if any(tool.name == "list_providers" for tool in tools):
                print("\nCalling list_providers()...")
                result = await client.call_tool("list_providers", {})
                # Handle the result properly - it could be a list or have content attribute
                if hasattr(result, 'content') and result.content:
                    providers = result.content[0].text
                elif isinstance(result, list) and result:
                    providers = str(result)
                else:
                    providers = str(result)
                print(f"Available providers: {providers}")
            
            # Test python_sandbox
            if any(tool.name == "python_sandbox" for tool in tools):
                print("\nTesting python_sandbox...")
                result = await client.call_tool(
                    "python_sandbox",
                    {"code": "print('Hello from MCP Router!')\nprint(2 + 2)"}
                )
                # Handle the result properly
                if hasattr(result, 'content') and result.content:
                    output = result.content[0].text
                elif isinstance(result, dict):
                    output = str(result)
                else:
                    output = str(result)
                print(f"Python output: {output}")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("MCP Router HTTP Transport Test")
    print("=" * 40)
    success = asyncio.run(test_http_connection())
    exit(0 if success else 1) 