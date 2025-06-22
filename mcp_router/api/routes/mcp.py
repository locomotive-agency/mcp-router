"""MCP protocol API endpoints."""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, status

from mcp_router.core.router import MCPRouterServer
from mcp_router.config.settings import Settings

router = APIRouter()

# Global MCP router instance
_mcp_router: Optional[MCPRouterServer] = None


def get_mcp_router() -> MCPRouterServer:
    """Get or create the global MCP router instance."""
    global _mcp_router
    if _mcp_router is None:
        settings = Settings()
        _mcp_router = MCPRouterServer(settings)
    return _mcp_router


@router.post("/initialize")
async def mcp_initialize(request: Dict[str, Any]) -> Dict[str, Any]:
    """MCP initialize endpoint."""
    try:
        router_instance = get_mcp_router()
        method = "initialize"
        params = request.get("params", {})
        result = await router_instance.handle_mcp_request(method, params)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Initialization failed: {str(e)}"
        )


@router.post("/initialized")
async def mcp_initialized(request: Dict[str, Any] = None) -> Dict[str, Any]:
    """MCP initialized notification endpoint."""
    try:
        router_instance = get_mcp_router()
        method = "initialized"
        params = request.get("params") if request else None
        result = await router_instance.handle_mcp_request(method, params)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Initialized notification failed: {str(e)}"
        )


@router.post("/tools/list")
async def mcp_list_tools(request: Dict[str, Any] = None) -> Dict[str, Any]:
    """List available tools from all MCP servers."""
    try:
        router_instance = get_mcp_router()
        method = "tools/list"
        params = request.get("params") if request else None
        result = await router_instance.handle_mcp_request(method, params)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tool listing failed: {str(e)}"
        )


@router.post("/tools/call")
async def mcp_call_tool(request: Dict[str, Any]) -> Dict[str, Any]:
    """Call a tool on an MCP server."""
    try:
        router_instance = get_mcp_router()
        method = "tools/call"
        params = request.get("params", {})
        result = await router_instance.handle_mcp_request(method, params)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tool call failed: {str(e)}"
        )


@router.post("/resources/list")
async def mcp_list_resources(request: Dict[str, Any] = None) -> Dict[str, Any]:
    """List available resources from all MCP servers."""
    try:
        router_instance = get_mcp_router()
        method = "resources/list"
        params = request.get("params") if request else None
        result = await router_instance.handle_mcp_request(method, params)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resource listing failed: {str(e)}"
        )


@router.post("/resources/read")
async def mcp_read_resource(request: Dict[str, Any]) -> Dict[str, Any]:
    """Read a resource from an MCP server."""
    try:
        router_instance = get_mcp_router()
        method = "resources/read"
        params = request.get("params", {})
        result = await router_instance.handle_mcp_request(method, params)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resource reading failed: {str(e)}"
        )


@router.post("/prompts/list")
async def mcp_list_prompts(request: Dict[str, Any] = None) -> Dict[str, Any]:
    """List available prompts from all MCP servers."""
    try:
        router_instance = get_mcp_router()
        method = "prompts/list"
        params = request.get("params") if request else None
        result = await router_instance.handle_mcp_request(method, params)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt listing failed: {str(e)}"
        )


@router.post("/prompts/get")
async def mcp_get_prompt(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get a prompt from an MCP server."""
    try:
        router_instance = get_mcp_router()
        method = "prompts/get"
        params = request.get("params", {})
        result = await router_instance.handle_mcp_request(method, params)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt retrieval failed: {str(e)}"
        ) 