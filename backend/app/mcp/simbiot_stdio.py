"""
SIMBIOT MCP Server - stdio transport for Claude Desktop.

Runs over standard input/output, enabling Claude Desktop to connect
directly to SIMBIOT tools without HTTP overhead.

Usage:
    # In Claude Desktop config (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "simbiot": {
          "command": "python",
          "args": ["-m", "app.mcp.simbiot_stdio"]
        }
      }
    }

    # Or run directly:
    python -m app.mcp.simbiot_stdio
"""

import asyncio
import sys
import json
import logging
from typing import Any, Dict, Optional

from app.mcp import SIMBIOTMCPServer

logger = logging.getLogger(__name__)


class MCPServerStdio:
    """
    MCP Server over stdio transport.

    Implements JSON-RPC 2.0 over stdin/stdout for Claude Desktop integration.
    """

    def __init__(self):
        self.server = SIMBIOTMCPServer()
        self.request_id = 0

    async def send_response(self, result: Any = None, error: Optional[Dict] = None, request_id: Optional[int] = None):
        """Send a JSON-RPC response to stdout."""
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
        }

        if error:
            response["error"] = error
        else:
            response["result"] = result

        # Write to stdout with newline
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    async def send_notification(self, method: str, params: Any = None):
        """Send a JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        sys.stdout.write(json.dumps(notification) + "\n")
        sys.stdout.flush()

    async def handle_initialize(self, params: Dict, request_id: int) -> Dict:
        """Handle initialize request from client."""
        logger.info(f"Client initializing: {params.get('clientInfo', {})}")

        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "simbiot-mcp", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        }

    async def handle_tools_list(self, request_id: int) -> Dict:
        """List available tools."""
        tools = self.server.list_tools()
        return {"tools": tools}

    async def handle_tools_call(self, params: Dict, request_id: int) -> Dict:
        """Execute a tool call."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            result = await self.server.call_tool(tool_name, **arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except ValueError as e:
            return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {"content": [{"type": "text", "text": f"Internal error: {str(e)}"}], "isError": True}

    async def handle_request(self, request: Dict):
        """Handle an incoming JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        logger.debug(f"Handling request: {method}")

        try:
            if method == "initialize":
                result = await self.handle_initialize(params, request_id)
                await self.send_response(result=result, request_id=request_id)

            elif method == "tools/list":
                result = await self.handle_tools_list(request_id)
                await self.send_response(result=result, request_id=request_id)

            elif method == "tools/call":
                result = await self.handle_tools_call(params, request_id)
                await self.send_response(result=result, request_id=request_id)

            elif method == "ping":
                await self.send_response(result={}, request_id=request_id)

            else:
                await self.send_response(
                    error={"code": -32601, "message": f"Method not found: {method}"}, request_id=request_id
                )

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            await self.send_response(
                error={"code": -32603, "message": f"Internal error: {str(e)}"}, request_id=request_id
            )

    async def run(self):
        """Main server loop reading from stdin."""
        logger.info("SIMBIOT MCP Server (stdio) starting...")

        # Send initialized notification
        await self.send_notification("notifications/initialized")

        # Read JSON-RPC requests from stdin
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                await self.handle_request(request)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
            except Exception as e:
                logger.error(f"Error processing request: {e}")


async def main():
    """Entry point for stdio MCP server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    server = MCPServerStdio()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
