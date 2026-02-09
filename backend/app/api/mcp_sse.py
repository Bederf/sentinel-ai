"""
SIMBIOT MCP Server - SSE transport for remote clients.

Runs over Server-Sent Events, enabling cloud-based Claude instances
to connect to SIMBIOT tools via HTTP.

Features:
- Robust keep-alive mechanism to prevent idle connection timeouts
- Heartbeat pings every 15 seconds with SSE comments as fallback
- Handles long idle periods (15+ hours) common in enterprise environments

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
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.mcp import SIMBIOTMCPServer

# Keep-alive configuration
SSE_HEARTBEAT_INTERVAL_SECONDS = 15  # Send heartbeat every 15 seconds
SSE_COMMENT_INTERVAL_SECONDS = 5     # Send SSE comment every 5 seconds (proxy keep-alive)
SSE_CONNECTION_TIMEOUT_SECONDS = 300 # Close connection after 5 min of no traffic from client

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
        """Generate SSE events for MCP protocol.

        Implements robust keep-alive to handle:
        - Proxy/firewall idle connection timeouts
        - Long idle periods (15+ hours)
        - Network interruptions
        """
        logger.info("SSE MCP connection established")
        connection_start = time.time()
        last_heartbeat = time.time()
        last_comment = time.time()

        # Send initialized notification
        yield await self.send_sse({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        })

        try:
            # Keep connection alive with dual keep-alive strategy
            while True:
                current_time = time.time()
                time_since_heartbeat = current_time - last_heartbeat
                time_since_comment = current_time - last_comment

                # Send SSE comment every 5 seconds (keeps proxies happy)
                if time_since_comment >= SSE_COMMENT_INTERVAL_SECONDS:
                    yield ": keep-alive comment\n\n"
                    last_comment = current_time
                    logger.debug("SSE keep-alive comment sent")

                # Send heartbeat ping every 15 seconds
                if time_since_heartbeat >= SSE_HEARTBEAT_INTERVAL_SECONDS:
                    yield await self.send_sse({
                        "jsonrpc": "2.0",
                        "method": "ping",
                        "params": {},
                        "_timestamp": current_time
                    })
                    last_heartbeat = current_time
                    connection_uptime = current_time - connection_start
                    logger.debug(f"SSE heartbeat sent (connection uptime: {connection_uptime:.0f}s)")

                # Sleep briefly to avoid busy-waiting
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            uptime = time.time() - connection_start
            logger.info(f"SSE MCP connection closed (uptime: {uptime:.0f}s)")
        except GeneratorExit:
            uptime = time.time() - connection_start
            logger.info(f"SSE MCP connection terminated (uptime: {uptime:.0f}s)")


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
    SSE endpoint for MCP protocol with robust keep-alive.

    Claude connects to this endpoint via SSE to use SIMBIOT tools.
    
    Keep-alive strategy:
    - SSE comment every 5 seconds (inexpensive, keeps proxies/firewalls active)
    - Heartbeat ping every 15 seconds (application-level heartbeat)
    - Standard SSE headers for persistent connections
    """
    server = get_sse_server()
    logger.info("New SSE MCP client connected")
    
    return StreamingResponse(
        server.event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "Transfer-Encoding": "chunked",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
            # Prevent nginx/proxy timeouts
            "Expires": "0",
            "Pragma": "no-cache"
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
