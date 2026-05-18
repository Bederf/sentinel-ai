"""
Asoba MCP REST API Wrapper

Provides HTTP endpoints for Asoba MCP tools.
Registered under /api/mcp/asoba
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mcp.asoba_server import asoba_mcp_server

logger = logging.getLogger(__name__)

router = APIRouter()


class ToolCallRequest(BaseModel):
    """Request body for tool calls."""

    tool: str
    arguments: dict[str, Any] = {}


@router.get("/tools")
async def list_tools() -> dict[str, Any]:
    """List available Asoba MCP tools."""
    return {
        "tools": asoba_mcp_server.list_tools(),
        "count": len(asoba_mcp_server.list_tools()),
    }


@router.post("/call")
async def call_tool(request: ToolCallRequest) -> dict[str, Any]:
    """Call an Asoba MCP tool."""
    logger.info(f"Asoba tool call: {request.tool}")

    result = await asoba_mcp_server.call_tool(request.tool, request.arguments)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result)

    return result


@router.get("/health")
async def health() -> dict[str, Any]:
    """Health check for Asoba integration."""
    return {
        "enabled": asoba_mcp_server.enabled,
        "api_key_configured": bool(asoba_mcp_server.api_key),
        "base_url": asoba_mcp_server.base_url,
        "site_mapping": asoba_mcp_server.site_mapping,
        "status": "healthy" if asoba_mcp_server.enabled else "disabled",
    }


@router.get("/site-mapping")
async def get_site_mapping() -> dict[str, Any]:
    """Get Sentinel -> Asoba site ID mapping."""
    return {
        "mapping": asoba_mcp_server.site_mapping,
        "count": len(asoba_mcp_server.site_mapping),
    }
