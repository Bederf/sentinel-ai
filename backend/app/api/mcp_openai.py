"""
OpenAI ChatGPT Connector & Microsoft 365 Copilot MCP Endpoint

Implements MCP over **Streamable HTTP** transport for:
- ChatGPT Deep Research connectors
- Microsoft 365 Copilot declarative agents
- Any MCP client supporting Streamable HTTP

Primary endpoint: POST /api/mcp/openai/mcp

Streamable HTTP is the recommended transport:
- SSE is deprecated for M365 Copilot (after Aug 2025)
- Simpler than SSE (no long-lived connections)
- Works across WAF/proxy configurations

Ref:
- https://platform.openai.com/docs/mcp
- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent
"""

import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse, Response

from app.mcp.openai_connector_server import get_openai_connector_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp/openai", tags=["MCP-OpenAI-Connector"])

# Separate router for well-known endpoint (no prefix)
wellknown_router = APIRouter(tags=["MCP-Discovery"])

# CORS headers for all responses
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Cache-Control",
}


def as_single_text_content(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format response as exactly one text content item with JSON-encoded string.

    This is the strict format required by OpenAI connectors:
    {
        "content": [
            {"type": "text", "text": "{...json string...}"}
        ]
    }
    """
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload)
            }
        ]
    }


def as_single_text_error(error_message: str) -> Dict[str, Any]:
    """Format error as single text content item."""
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"error": error_message})
            }
        ],
        "isError": True
    }


class MCPStreamableHTTPHandler:
    """
    MCP Server handler for Streamable HTTP transport.

    Streamable HTTP transport spec:
    - Client sends JSON-RPC via POST to MCP endpoint
    - Server responds with JSON (or streams for long responses)
    - Accept header: application/json, text/event-stream
    """

    def __init__(self):
        self.server = get_openai_connector_server()

    async def handle_initialize(self, params: Dict) -> Dict:
        """Handle MCP initialize request."""
        client_info = params.get("clientInfo", {})
        logger.info(f"MCP Initialize: {client_info.get('name', 'unknown')} v{client_info.get('version', '?')}")

        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "sentinel-bms-connector",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
            }
        }

    async def handle_tools_list(self) -> Dict:
        """List available tools."""
        tools = self.server.list_tools()
        logger.debug(f"MCP tools/list: returning {len(tools)} tools")
        return {"tools": tools}

    async def handle_tools_call(self, params: Dict) -> Dict:
        """
        Execute tool call with OpenAI connector response format.

        Returns exactly one content item of type text with JSON-encoded string.
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        logger.info(f"MCP tools/call: {tool_name}({json.dumps(arguments)[:100]})")

        try:
            result = await self.server.call_tool(tool_name, **arguments)
            return as_single_text_content(result)

        except ValueError as e:
            logger.warning(f"MCP tool error: {e}")
            return as_single_text_error(str(e))

        except Exception as e:
            logger.error(f"MCP internal error: {e}", exc_info=True)
            return as_single_text_error(f"Internal error: {str(e)}")

    async def handle_request(self, request_body: Dict) -> Dict:
        """
        Handle incoming JSON-RPC request.

        Returns full JSON-RPC response envelope.
        """
        method = request_body.get("method")
        params = request_body.get("params", {})
        request_id = request_body.get("id")

        logger.debug(f"MCP request: method={method}, id={request_id}")

        try:
            if method == "initialize":
                result = await self.handle_initialize(params)

            elif method == "notifications/initialized":
                # Client notification - no response needed for notifications
                # But we still return empty result for Streamable HTTP
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {}
                }

            elif method == "tools/list":
                result = await self.handle_tools_list()

            elif method == "tools/call":
                result = await self.handle_tools_call(params)

            elif method == "ping":
                result = {}

            else:
                logger.warning(f"MCP unknown method: {method}")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }

        except Exception as e:
            logger.error(f"MCP request error: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }


# Singleton handler
_mcp_handler: Optional[MCPStreamableHTTPHandler] = None


def get_mcp_handler() -> MCPStreamableHTTPHandler:
    """Get or create MCP handler singleton."""
    global _mcp_handler
    if _mcp_handler is None:
        _mcp_handler = MCPStreamableHTTPHandler()
    return _mcp_handler


# =============================================================================
# Streamable HTTP MCP Endpoint (Primary)
# =============================================================================

@router.post("/mcp")
async def mcp_streamable_http_endpoint(
    request: Request,
    accept: Optional[str] = Header(default="application/json")
):
    """
    Streamable HTTP MCP endpoint.

    This is the PRIMARY endpoint for:
    - ChatGPT Deep Research connectors
    - Microsoft 365 Copilot declarative agents

    URL: POST https://your-domain.com/api/mcp/openai/mcp

    Accepts:
    - Content-Type: application/json
    - Accept: application/json, text/event-stream

    Test with:
        curl -X POST https://your-domain.com/api/mcp/openai/mcp \\
          -H "Content-Type: application/json" \\
          -H "Accept: application/json, text/event-stream" \\
          -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"MCP invalid JSON: {e}")
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error: Invalid JSON"
                }
            },
            headers=CORS_HEADERS
        )

    handler = get_mcp_handler()
    response = await handler.handle_request(body)

    return JSONResponse(
        content=response,
        headers=CORS_HEADERS
    )


@router.options("/mcp")
async def mcp_options():
    """Handle CORS preflight for MCP endpoint."""
    return Response(
        status_code=200,
        headers={
            **CORS_HEADERS,
            "Access-Control-Max-Age": "86400",
        }
    )


@router.get("/mcp")
async def mcp_get_info():
    """
    GET on MCP endpoint returns server info.

    Useful for connector discovery and health checks.
    """
    server = get_openai_connector_server()
    return JSONResponse(
        content={
            "name": "sentinel-bms-connector",
            "version": "1.0.0",
            "description": "SENTINEL BMS Intelligence Platform - Building Management Data Connector",
            "protocol": "MCP",
            "protocolVersion": "2024-11-05",
            "transport": "streamable-http",
            "tools": ["search", "fetch"],
            "documents_indexed": len(server._documents or []) if server._documents else "not loaded"
        },
        headers=CORS_HEADERS
    )


# =============================================================================
# Health & Info Endpoints
# =============================================================================

@router.get("/info")
async def openai_connector_info():
    """Get connector information and available tools."""
    server = get_openai_connector_server()
    return JSONResponse(
        content={
            "name": "sentinel-bms-connector",
            "version": "1.0.0",
            "description": "SENTINEL BMS Intelligence Platform - Building Management Data Connector",
            "mcp_version": "2024-11-05",
            "transport": "streamable-http",
            "mcp_endpoint": "/api/mcp/openai/mcp",
            "tools": server.list_tools(),
            "capabilities": {
                "search": "Search BMS data including buildings, equipment, alerts, predictions",
                "fetch": "Retrieve full document content by ID"
            }
        },
        headers=CORS_HEADERS
    )


@router.get("/health")
async def openai_connector_health():
    """Health check endpoint - publicly accessible for external connectivity tests."""
    server = get_openai_connector_server()
    server._ensure_index()

    return JSONResponse(
        content={
            "status": "healthy",
            "documents_indexed": len(server._documents or []),
            "timestamp": datetime.now().isoformat(),
            "mcp_endpoint": "/api/mcp/openai/mcp",
            "transport": "streamable-http",
            "tools": ["search", "fetch"]
        },
        headers=CORS_HEADERS
    )


@router.get("/stats")
async def openai_connector_stats():
    """Get detailed index statistics."""
    server = get_openai_connector_server()
    return JSONResponse(
        content=server.get_stats(),
        headers=CORS_HEADERS
    )


@router.post("/refresh")
async def openai_connector_refresh():
    """Force refresh the document index."""
    server = get_openai_connector_server()
    server.refresh_index()
    return JSONResponse(
        content={
            "status": "refreshed",
            "stats": server.get_stats()
        },
        headers=CORS_HEADERS
    )


# =============================================================================
# Legacy SSE Endpoint (kept for backwards compatibility)
# =============================================================================

@router.get("/sse")
@router.get("/sse/")
async def sse_legacy_redirect():
    """
    Legacy SSE endpoint - redirects to info with deprecation notice.

    SSE transport is deprecated for Microsoft 365 Copilot.
    Use Streamable HTTP at /api/mcp/openai/mcp instead.
    """
    return JSONResponse(
        content={
            "message": "SSE transport is deprecated. Use Streamable HTTP instead.",
            "mcp_endpoint": "/api/mcp/openai/mcp",
            "documentation": "https://modelcontextprotocol.io/specification/2025-06-18/basic/transports"
        },
        headers=CORS_HEADERS
    )


@router.post("/sse")
@router.post("/sse/")
async def sse_legacy_post(request: Request):
    """
    Legacy SSE POST - forwards to Streamable HTTP handler.

    For backwards compatibility with existing integrations.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON"},
            headers=CORS_HEADERS
        )

    handler = get_mcp_handler()
    response = await handler.handle_request(body)

    return JSONResponse(
        content=response,
        headers=CORS_HEADERS
    )


@router.options("/sse")
@router.options("/sse/")
async def sse_options():
    """Handle CORS preflight for legacy SSE endpoint."""
    return Response(
        status_code=200,
        headers={
            **CORS_HEADERS,
            "Access-Control-Max-Age": "86400",
        }
    )


# =============================================================================
# Well-Known MCP Discovery Endpoint
# =============================================================================

@wellknown_router.get("/.well-known/mcp.json")
async def mcp_discovery():
    """
    MCP Discovery endpoint for ChatGPT connectors and M365 Copilot.

    This is the standard location for MCP server discovery.
    Returns server info and endpoint URL.
    """
    return JSONResponse(
        content={
            "name": "sentinel-bms-connector",
            "version": "1.0.0",
            "description": "SENTINEL BMS Intelligence Platform - Building Management Data Connector",
            "mcp": {
                "version": "2024-11-05",
                "transport": "streamable-http",
                "endpoint": "/api/mcp/openai/mcp"
            },
            "tools": ["search", "fetch"],
            "capabilities": {
                "search": "Search BMS data including buildings, equipment, alerts, predictions",
                "fetch": "Retrieve full document content by ID"
            }
        },
        headers=CORS_HEADERS
    )


@wellknown_router.options("/.well-known/mcp.json")
async def mcp_discovery_options():
    """Handle CORS preflight for MCP discovery endpoint."""
    return Response(
        status_code=200,
        headers={
            **CORS_HEADERS,
            "Access-Control-Max-Age": "86400",
        }
    )
