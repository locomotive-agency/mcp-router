"""Middleware for hierarchical tool discovery in MCP Router"""

from typing import Dict, Any, Callable, Awaitable
from fastmcp.server.middleware import Middleware, MiddlewareContext
import logging

log = logging.getLogger(__name__)


class ProviderFilterMiddleware(Middleware):
    """
    Middleware that implements hierarchical tool discovery.

    - Without provider param: shows only discovery tools (python_sandbox, list_providers)
    - With provider param: shows only that provider's tools with prefixes removed
    """

    async def on_tools_list(
        self,
        ctx: MiddlewareContext,
        call_next: Callable[[MiddlewareContext], Awaitable[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        Filter tool listings based on provider parameter.

        When no provider is specified, only show discovery tools.
        When a provider is specified, show only that provider's tools.

        Args:
            ctx: Middleware context containing request parameters
            call_next: Next handler in the middleware chain

        Returns:
            Filtered tool listing response
        """
        # Extract provider from the request parameters
        provider = ctx.params.get("provider") if ctx.params else None

        # Get the full tool list from the proxy
        result = await call_next(ctx)

        if provider:
            # Filter to show only tools from the specified provider
            # The proxy will have prefixed tools with "servername_toolname"
            filtered_tools = []
            for tool in result.get("tools", []):
                if tool["name"].startswith(f"{provider}_"):
                    # Create a copy and remove the prefix for cleaner presentation
                    tool_copy = tool.copy()
                    tool_copy["name"] = tool["name"][len(provider) + 1:]
                    filtered_tools.append(tool_copy)

            result["tools"] = filtered_tools
            log.info(f"Filtered tools for provider '{provider}': {len(filtered_tools)} tools")
        else:
            # Show only discovery tools when no provider specified
            discovery_tools = ["python_sandbox", "list_providers"]
            result["tools"] = [t for t in result.get("tools", []) if t["name"] in discovery_tools]
            log.info("Showing discovery tools only")

        return result

    async def on_tool_call(
        self,
        ctx: MiddlewareContext,
        call_next: Callable[[MiddlewareContext], Awaitable[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        Add provider prefix to tool calls when provider is specified.

        This ensures tool calls are routed to the correct sub-server.

        Args:
            ctx: Middleware context containing request parameters
            call_next: Next handler in the middleware chain

        Returns:
            Tool call response from the appropriate sub-server
        """
        if ctx.params and "arguments" in ctx.params:
            args = ctx.params["arguments"]
            provider = args.pop("provider", None)

            if provider and "_" not in ctx.params.get("name", ""):
                # Add provider prefix to route to correct sub-server
                original_name = ctx.params["name"]
                ctx.params["name"] = f"{provider}_{original_name}"
                log.info(f"Rewriting tool call: {original_name} -> {ctx.params['name']}")

        return await call_next(ctx)
