"""
MCP (Model Context Protocol) API Endpoints.

Exposes SIMBIOT MCP Server tools via REST API for Claude integration.

Endpoints:
- GET  /api/mcp/simbiot/tools - List available tools with schemas
- POST /api/mcp/simbiot/call  - Execute a tool by name
- GET  /api/mcp/simbiot/info  - Server manifest/info
- GET  /api/mcp/simbiot/tools/{tool_name} - Get specific tool schema
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mcp import SIMBIOTMCPServer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mcp/simbiot", tags=["MCP"])

# Singleton server instance
_server: SIMBIOTMCPServer | None = None


def get_server() -> SIMBIOTMCPServer:
    """Get or create the SIMBIOT MCP server singleton."""
    global _server
    if _server is None:
        _server = SIMBIOTMCPServer()
    return _server


# ============================================================================
# Pydantic Models
# ============================================================================


class ToolCallRequest(BaseModel):
    """Request body for tool execution."""

    tool_name: str
    arguments: dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    """Response from tool execution."""

    tool_name: str
    result: Any
    error: str | None = None


class MCPServerInfo(BaseModel):
    """Server information and capabilities."""

    name: str
    version: str
    description: str
    tool_count: int
    capabilities: dict[str, bool]


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/tools")
async def list_tools() -> list[dict[str, Any]]:
    """
    List all SIMBIOT MCP tools with their JSON schemas.

    Returns:
        Array of tool definitions including name, description, and input_schema.
    """
    server = get_server()
    return server.list_tools()


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest) -> ToolCallResponse:
    """
    Execute an MCP tool by name with provided arguments.

    Args:
        request: Tool name and arguments to execute.

    Returns:
        Tool execution result or error message.
    """
    server = get_server()
    try:
        result = await server.call_tool(request.tool_name, **request.arguments)
        return ToolCallResponse(tool_name=request.tool_name, result=result)
    except ValueError as e:
        # Tool not found or invalid arguments
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Tool execution error for {request.tool_name}: {e}")
        return ToolCallResponse(tool_name=request.tool_name, result=None, error=str(e))


@router.get("/info", response_model=MCPServerInfo)
async def server_info() -> MCPServerInfo:
    """
    Get SIMBIOT MCP server information.

    Returns:
        Server name, version, description, tool count, and capabilities.
    """
    server = get_server()
    return MCPServerInfo(
        name="simbiot-mcp",
        version="1.0.0",
        description=(
            "SIMBIOT Building Intelligence MCP Server - Provides building data, "
            "asset management, and BMS device control tools for AI integration."
        ),
        tool_count=len(server.list_tools()),
        capabilities={
            "tools": True,
            "resources": False,  # Future: building:// URIs
            "prompts": False,  # Future: analyze_asset, diagnose_equipment, etc.
            "logging": True,
        },
    )


@router.get("/tools/{tool_name}")
async def get_tool_schema(tool_name: str) -> dict[str, Any]:
    """
    Get JSON schema for a specific tool.

    Args:
        tool_name: Name of the tool to get schema for.

    Returns:
        Tool definition including name, description, and input_schema.

    Raises:
        HTTPException 404: Tool not found.
    """
    server = get_server()
    schema = server.get_tool_schema(tool_name)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return schema
