"""
SIMBIOT MCP Server - SSE transport for remote clients.

Runs over Server-Sent Events, enabling cloud-based Claude instances
to connect to SIMBIOT tools via HTTP.

Usage:
    # Claude connects via SSE to:
    GET /api/mcp/sse

    # MCP messages sent as SSE events:
    event: message
    data: {"jsonrpc": "2.0", "method": "tools/list", ...}
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.mcp import SIMBIOTMCPServer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mcp/sse", tags=["MCP-SSE"])


class MCPServerSSE:
    """
    MCP Server over SSE transport.

    Implements JSON-RPC 2.0 over Server-Sent Events for remote clients.
    """

    def __init__(self):
        self.server = SIMBIOTMCPServer()

    async def send_sse(self, data: Dict):
        """Format data as SSE event."""
        return f"event: message\ndata: {json.dumps(data)}\n\n"

    async def handle_initialize(self, params: Dict) -> Dict:
        """Handle initialize request."""
        logger.info(f"SSE client initializing: {params.get('clientInfo', {})}")

        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "simbiot-mcp",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
            }
        }

    async def handle_tools_list(self) -> Dict:
        """List available tools."""
        tools = self.server.list_tools()
        return {"tools": tools}

    async def handle_tools_call(self, params: Dict) -> Dict:
        """Execute a tool call."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            result = await self.server.call_tool(tool_name, **arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        except ValueError as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: {str(e)}"
                    }
                ],
                "isError": True
            }
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Internal error: {str(e)}"
                    }
                ],
                "isError": True
            }

    async def handle_request(self, request: Dict) -> Optional[Dict]:
        """Handle an incoming JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})

        logger.debug(f"Handling SSE request: {method}")

        try:
            if method == "initialize":
                return await self.handle_initialize(params)

            elif method == "tools/list":
                return await self.handle_tools_list()

            elif method == "tools/call":
                return await self.handle_tools_call(params)

            elif method == "ping":
                return {}

            else:
                return {
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            return {
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }

    async def event_stream(self):
        """Generate SSE events for MCP protocol."""
        logger.info("SSE MCP connection established")

        # Send initialized notification
        yield await self.send_sse({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        })

        # In a full implementation, this would be a bidirectional stream
        # For now, we'll provide a simple message queue approach
        try:
            # Keep connection alive with heartbeat
            while True:
                await asyncio.sleep(30)
                yield await self.send_sse({
                    "jsonrpc": "2.0",
                    "method": "ping",
                    "params": {}
                })
        except asyncio.CancelledError:
            logger.info("SSE MCP connection closed")


# Singleton instance
_sse_server: Optional[MCPServerSSE] = None


def get_sse_server() -> MCPServerSSE:
    """Get or create SSE MCP server singleton."""
    global _sse_server
    if _sse_server is None:
        _sse_server = MCPServerSSE()
    return _sse_server


@router.get("")
async def mcp_sse_endpoint():
    """
    SSE endpoint for MCP protocol.

    Claude connects to this endpoint via SSE to use SIMBIOT tools.
    """
    server = get_sse_server()
    return StreamingResponse(
        server.event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/request")
async def mcp_request_endpoint(request: Dict):
    """
    HTTP POST endpoint for MCP requests (alternative to SSE).

    Useful for testing and clients that don't support SSE.
    """
    server = get_sse_server()
    response = await server.handle_request(request)

    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": response,
        "error": response.get("error") if isinstance(response, dict) and "error" in response else None
    }
