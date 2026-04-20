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
import secrets
import time
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config.settings import settings
from app.mcp import SIMBIOTMCPServer
from app.models.auth import AuthContext

# Keep-alive configuration
SSE_HEARTBEAT_INTERVAL_SECONDS = 15  # Send heartbeat every 15 seconds
SSE_COMMENT_INTERVAL_SECONDS = 5  # Send SSE comment every 5 seconds (proxy keep-alive)
SSE_CONNECTION_TIMEOUT_SECONDS = 300  # Close connection after 5 min of no traffic from client

# Payload size guard
_MAX_PAYLOAD_BYTES = 1_048_576  # 1 MB max request payload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 Allowed methods
# ---------------------------------------------------------------------------

_ALLOWED_JSONRPC_METHODS = frozenset(
    {
        "initialize",
        "tools/list",
        "tools/call",
        "ping",
        "notifications/initialized",
    }
)

_ALLOWED_JSONRPC_FIELDS = frozenset({"jsonrpc", "method", "params", "id"})


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope validation
# ---------------------------------------------------------------------------


def _validate_jsonrpc_envelope(data: dict) -> tuple[bool, str | None, int]:
    """Validate a JSON-RPC 2.0 envelope.

    Returns:
        (True, None, 0) if valid.
        (False, error_message, http_status) if invalid.
    """
    # Check for unknown top-level fields
    unknown = set(data.keys()) - _ALLOWED_JSONRPC_FIELDS
    if unknown:
        return False, f"Unknown top-level fields: {unknown}", 400

    # jsonrpc version must be "2.0"
    if data.get("jsonrpc") != "2.0":
        return False, "jsonrpc must be '2.0'", 400

    # method must be a known string
    method = data.get("method")
    if not isinstance(method, str) or method not in _ALLOWED_JSONRPC_METHODS:
        return False, f"Unknown method: {method}", 400

    # id is required for non-notification methods
    is_notification = isinstance(method, str) and method.startswith("notifications/")
    if not is_notification and "id" not in data:
        return False, "Missing required field: id", 400

    # params must be a dict if present
    if "params" in data and not isinstance(data["params"], dict):
        return False, "params must be an object (dict), not array or scalar", 400

    return True, None, 0


# ---------------------------------------------------------------------------
# Host / Origin enforcement
# ---------------------------------------------------------------------------

_LOCALHOST_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _validate_host_origin(request) -> None:
    """Enforce Host/Origin localhost restriction in non-production environments.

    In production mode (settings.environment == 'production'), all hosts are allowed.
    Otherwise, Host and Origin headers must resolve to localhost/127.0.0.1.

    Raises HTTPException(403) if validation fails.
    """
    if settings.environment == "production":
        return

    # Check Host header
    host_header = request.headers.get("host", "")
    host_name = host_header.split(":")[0].lower() if host_header else ""
    if host_name and host_name not in _LOCALHOST_HOSTS:
        raise HTTPException(status_code=403, detail="Non-localhost Host header rejected in development mode")

    # Check Origin header (if present)
    origin_header = request.headers.get("origin")
    if origin_header:
        parsed = urlparse(origin_header)
        origin_host = parsed.hostname or ""
        if origin_host not in _LOCALHOST_HOSTS:
            raise HTTPException(status_code=403, detail="Non-localhost Origin header rejected in development mode")


# ---------------------------------------------------------------------------
# MCP Tickets — single-use session handover tokens
# ---------------------------------------------------------------------------

_MCP_TICKETS: dict[str, dict] = {}


def _create_mcp_ticket(auth_ctx: AuthContext) -> str:
    """Create a single-use ticket that carries the given auth context.

    Returns the ticket token string.
    """
    ticket_id = secrets.token_urlsafe(32)
    _MCP_TICKETS[ticket_id] = {
        "auth_ctx": auth_ctx,
        "created_at": time.time(),
        "used": False,
    }
    return ticket_id


def _validate_mcp_ticket(ticket: str) -> AuthContext | None:
    """Validate and consume a single-use MCP ticket.

    Returns the AuthContext if the ticket is valid and unused, else None.
    The ticket is marked as used on successful validation.
    """
    entry = _MCP_TICKETS.get(ticket)
    if entry is None:
        return None
    if entry["used"]:
        return None
    entry["used"] = True
    return entry["auth_ctx"]


router = APIRouter(prefix="/api/mcp/sse", tags=["MCP-SSE"])


class MCPServerSSE:
    """
    MCP Server over SSE transport.

    Implements JSON-RPC 2.0 over Server-Sent Events for remote clients.
    """

    def __init__(self):
        self.server = SIMBIOTMCPServer()

    async def send_sse(self, data: dict):
        """Format data as SSE event."""
        return f"event: message\ndata: {json.dumps(data)}\n\n"

    async def handle_initialize(self, params: dict) -> dict:
        """Handle initialize request."""
        logger.info(f"SSE client initializing: {params.get('clientInfo', {})}")

        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "simbiot-mcp", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        }

    async def handle_tools_list(self) -> dict:
        """List available tools."""
        tools = self.server.list_tools()
        return {"tools": tools}

    async def handle_tools_call(self, params: dict, auth_ctx=None) -> dict:
        """Execute a tool call."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            kwargs = dict(arguments)
            if auth_ctx is not None:
                kwargs["_auth_context"] = auth_ctx
            result = await self.server.call_tool(tool_name, **kwargs)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except ValueError as e:
            request_id = str(uuid.uuid4())
            logger.warning(f"Tool input error [{request_id}]: {e}")
            return {
                "content": [
                    {"type": "text", "text": json.dumps({"error": "invalid_request", "request_id": request_id})}
                ],
                "isError": True,
            }
        except Exception as e:
            request_id = str(uuid.uuid4())
            logger.error(f"Tool execution error [{request_id}]: {e}", exc_info=True)
            return {
                "content": [
                    {"type": "text", "text": json.dumps({"error": "internal_error", "request_id": request_id})}
                ],
                "isError": True,
            }

    async def handle_request(self, request: dict) -> dict | None:
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
                return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            return {"error": {"code": -32603, "message": "Internal error"}}

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
        yield await self.send_sse({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

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
                    yield await self.send_sse(
                        {"jsonrpc": "2.0", "method": "ping", "params": {}, "_timestamp": current_time}
                    )
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
_sse_server: MCPServerSSE | None = None


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
            "Pragma": "no-cache",
        },
    )


@router.post("/request")
async def mcp_request_endpoint(request: dict):
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
        "error": response.get("error") if isinstance(response, dict) and "error" in response else None,
    }
