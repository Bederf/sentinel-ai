"""
OpenAI ChatGPT Connector MCP SSE Endpoint

Implements MCP over SSE for OpenAI connectors with strict response formatting:
- Exactly one content item of type "text"
- Text field contains JSON-encoded string

URL must end in /sse/ for OpenAI connectors.

Ref: https://platform.openai.com/docs/mcp
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.mcp.openai_connector_server import get_openai_connector_server

logger = logging.getLogger(__name__)

# Note: URL ends with /sse which will become /sse/ with trailing slash
router = APIRouter(prefix="/api/mcp/openai", tags=["MCP-OpenAI-Connector"])


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


class OpenAIMCPServerSSE:
    """
    MCP Server over SSE transport for OpenAI connectors.

    Strict compliance with OpenAI connector requirements:
    - Only search and fetch tools
    - Single text content item responses
    - JSON-encoded text field
    """

    def __init__(self):
        self.server = get_openai_connector_server()
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def send_sse(self, data: Dict) -> str:
        """Format data as SSE event."""
        return f"event: message\ndata: {json.dumps(data)}\n\n"

    async def handle_initialize(self, params: Dict) -> Dict:
        """Handle MCP initialize request."""
        client_info = params.get("clientInfo", {})
        logger.info(f"OpenAI Connector: Client initializing - {client_info.get('name', 'unknown')}")

        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "sentinel-bms-connector",
                "version": "1.0.0",
                "description": "SENTINEL BMS Intelligence Platform - Building Management Data Connector"
            },
            "capabilities": {
                "tools": {}
            }
        }

    async def handle_tools_list(self) -> Dict:
        """List available tools (search and fetch only)."""
        tools = self.server.list_tools()
        return {"tools": tools}

    async def handle_tools_call(self, params: Dict) -> Dict:
        """
        Execute tool call with strict OpenAI connector response format.

        Returns exactly one content item of type text with JSON-encoded string.
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        logger.info(f"OpenAI Connector: Tool call - {tool_name}({arguments})")

        try:
            result = await self.server.call_tool(tool_name, **arguments)
            # Return single text content with JSON-encoded payload
            return as_single_text_content(result)

        except ValueError as e:
            logger.warning(f"OpenAI Connector: Tool error - {e}")
            return as_single_text_error(str(e))

        except Exception as e:
            logger.error(f"OpenAI Connector: Internal error - {e}", exc_info=True)
            return as_single_text_error(f"Internal error: {str(e)}")

    async def handle_request(self, request: Dict) -> Optional[Dict]:
        """Handle incoming JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        logger.debug(f"OpenAI Connector: Request - {method}")

        try:
            if method == "initialize":
                result = await self.handle_initialize(params)

            elif method == "tools/list":
                result = await self.handle_tools_list()

            elif method == "tools/call":
                result = await self.handle_tools_call(params)

            elif method == "ping":
                result = {}

            elif method == "notifications/initialized":
                # Client notification, no response needed
                return None

            else:
                return {
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            return result

        except Exception as e:
            logger.error(f"OpenAI Connector: Request error - {e}", exc_info=True)
            return {
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }

    async def event_stream(self, request: Request):
        """Generate SSE events for MCP protocol."""
        logger.info("OpenAI Connector: SSE connection established")

        # Send server ready notification
        yield await self.send_sse({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        })

        try:
            # Keep connection alive with periodic heartbeat
            heartbeat_interval = 25  # seconds
            last_heartbeat = datetime.now()

            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info("OpenAI Connector: Client disconnected")
                    break

                # Check message queue (non-blocking)
                try:
                    message = self._message_queue.get_nowait()
                    yield await self.send_sse(message)
                except asyncio.QueueEmpty:
                    pass

                # Send heartbeat
                now = datetime.now()
                if (now - last_heartbeat).total_seconds() >= heartbeat_interval:
                    yield f": heartbeat\n\n"  # SSE comment for keepalive
                    last_heartbeat = now

                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("OpenAI Connector: SSE connection cancelled")
        except Exception as e:
            logger.error(f"OpenAI Connector: SSE error - {e}", exc_info=True)


# Singleton instance
_openai_sse_server: Optional[OpenAIMCPServerSSE] = None


def get_openai_sse_server() -> OpenAIMCPServerSSE:
    """Get or create SSE server singleton."""
    global _openai_sse_server
    if _openai_sse_server is None:
        _openai_sse_server = OpenAIMCPServerSSE()
    return _openai_sse_server


# =============================================================================
# SSE Endpoints
# =============================================================================

@router.get("/sse/")
@router.get("/sse")
async def openai_mcp_sse_endpoint(request: Request):
    """
    SSE endpoint for OpenAI ChatGPT connectors.

    URL: /api/mcp/openai/sse/

    OpenAI connectors require the URL to end in /sse/
    This endpoint provides server-sent events for MCP protocol.
    """
    server = get_openai_sse_server()
    return StreamingResponse(
        server.event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS"
        }
    )


@router.post("/sse/")
@router.post("/sse")
async def openai_mcp_request_endpoint(request: Dict):
    """
    HTTP POST endpoint for MCP tool calls.

    OpenAI connectors send tool requests via POST to the SSE endpoint.
    """
    server = get_openai_sse_server()
    response = await server.handle_request(request)

    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": response
    }


@router.options("/sse/")
@router.options("/sse")
async def openai_mcp_options():
    """Handle CORS preflight for OpenAI connectors."""
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Cache-Control",
            "Access-Control-Max-Age": "86400",
        }
    )


# =============================================================================
# Health & Info Endpoints
# =============================================================================

@router.get("/info")
async def openai_connector_info():
    """Get connector information and available tools."""
    server = get_openai_connector_server()
    return {
        "name": "sentinel-bms-connector",
        "version": "1.0.0",
        "description": "SENTINEL BMS Intelligence Platform - Building Management Data Connector",
        "mcp_version": "2024-11-05",
        "sse_endpoint": "/api/mcp/openai/sse/",
        "tools": server.list_tools(),
        "capabilities": {
            "search": "Search BMS data including buildings, equipment, alerts",
            "fetch": "Retrieve full document content by ID"
        }
    }


@router.get("/health")
async def openai_connector_health():
    """Health check endpoint - publicly accessible for external connectivity tests."""
    from fastapi.responses import JSONResponse

    server = get_openai_connector_server()
    # Trigger index build to check health
    server._ensure_index()

    return JSONResponse(
        content={
            "status": "healthy",
            "documents_indexed": len(server._documents or []),
            "timestamp": datetime.now().isoformat(),
            "mcp_endpoint": "/api/mcp/openai/sse/",
            "tools": ["search", "fetch"]
        },
        headers={
            "Access-Control-Allow-Origin": "*",
        }
    )


@router.get("/stats")
async def openai_connector_stats():
    """Get detailed index statistics."""
    server = get_openai_connector_server()
    return server.get_stats()


@router.post("/refresh")
async def openai_connector_refresh():
    """Force refresh the document index."""
    server = get_openai_connector_server()
    server.refresh_index()
    return {
        "status": "refreshed",
        "stats": server.get_stats()
    }
