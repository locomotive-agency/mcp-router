import sys
import types
import pytest
import asyncio

# Create stubs for fastmcp middleware classes if fastmcp is not installed
if 'fastmcp.server.middleware' not in sys.modules:
    fastmcp = types.ModuleType("fastmcp")
    server_mod = types.ModuleType("fastmcp.server")
    middleware_mod = types.ModuleType("fastmcp.server.middleware")

    class _BaseMiddleware:  # Minimal stub base class
        pass

    class _MiddlewareContext:
        """Light-weight stand-in for FastMCP MiddlewareContext"""
        def __init__(self, params=None):
            self.params = params

    middleware_mod.Middleware = _BaseMiddleware
    middleware_mod.MiddlewareContext = _MiddlewareContext

    server_mod.middleware = middleware_mod
    fastmcp.server = server_mod

    sys.modules['fastmcp'] = fastmcp
    sys.modules['fastmcp.server'] = server_mod
    sys.modules['fastmcp.server.middleware'] = middleware_mod

# Now we can safely import the middleware under test
from mcp_router.middleware import ProviderFilterMiddleware  # noqa: E402


class FakeCtx:  # Helper context object mimicking FastMCP's MiddlewareContext
    def __init__(self, params=None):
        self.params = params or {}


@pytest.mark.asyncio
async def test_on_tools_list_no_provider():
    """When no provider is specified, only discovery tools should be returned."""
    middleware = ProviderFilterMiddleware()

    # Simulated full tool list returned by the proxy
    original_tools = [
        {"name": "python_sandbox"},
        {"name": "list_providers"},
        {"name": "server1_toolA"},
        {"name": "server1_toolB"},
        {"name": "server2_toolA"},
    ]

    async def call_next(ctx):  # Dummy downstream function
        return {"tools": list(original_tools)}

    ctx = FakeCtx(params={})
    result = await middleware.on_tools_list(ctx, call_next)

    # Expect only discovery tools
    tool_names = [t["name"] for t in result["tools"]]
    assert tool_names == ["python_sandbox", "list_providers"]


@pytest.mark.asyncio
async def test_on_tools_list_with_provider():
    """When a provider is specified, only that provider's tools should be listed without prefix."""
    middleware = ProviderFilterMiddleware()

    original_tools = [
        {"name": "python_sandbox"},
        {"name": "list_providers"},
        {"name": "server1_toolA"},
        {"name": "server1_toolB"},
        {"name": "server2_toolA"},
    ]

    async def call_next(ctx):
        return {"tools": list(original_tools)}

    ctx = FakeCtx(params={"provider": "server1"})
    result = await middleware.on_tools_list(ctx, call_next)

    tool_names = sorted(t["name"] for t in result["tools"])
    assert tool_names == ["toolA", "toolB"]


@pytest.mark.asyncio
async def test_on_tool_call_rewrites_name():
    """on_tool_call should prepend provider prefix and remove provider argument."""
    middleware = ProviderFilterMiddleware()

    async def call_next(ctx):
        # Return ctx.params for easy inspection
        return ctx.params

    ctx = FakeCtx(params={"name": "toolA", "arguments": {"param": 1, "provider": "server1"}})
    result = await middleware.on_tool_call(ctx, call_next)

    assert result["name"] == "server1_toolA"
    # provider argument should be removed
    assert "provider" not in result["arguments"] 