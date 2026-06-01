"""
Asoba MCP Server - stdio Transport Wrapper

Enables Claude Desktop integration via stdio transport.
Reads JSON-RPC requests from stdin, writes responses to stdout.

Usage (Claude Desktop config):
    {
      "mcpServers": {
        "asoba": {
          "command": "python",
          "args": ["-m", "app.mcp.asoba_stdio"],
          "cwd": "/opt/bms-intelligence/backend",
          "env": {
            "PYTHONPATH": "/opt/bms-intelligence/backend",
            "ASOBA_API_KEY": "<your_key>",
            "ASOBA_ENABLED": "true",
            "ASOBA_SITE_MAPPING": "site-002:ltm-sandton-001"
          }
        }
      }
    }
"""

import asyncio
import json
import logging
import sys

# Configure logging to stderr (keep stdout clean for JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


async def main():
    """Main stdio server loop."""
    from app.mcp.asoba_server import asoba_mcp_server

    logger.info("Asoba MCP Server starting...")
    logger.info(f"Enabled: {asoba_mcp_server.enabled}")
    logger.info(f"Base URL: {asoba_mcp_server.base_url}")
    logger.info(f"Site mapping: {asoba_mcp_server.site_mapping}")

    while True:
        try:
            # Read line from stdin
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)

            if not line:
                # EOF reached
                logger.info("EOF reached, shutting down")
                break

            line = line.strip()
            if not line:
                continue

            # Parse JSON-RPC request
            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                _send_error(None, -32700, "Parse error")
                continue

            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            logger.debug(f"Request: method={method}, id={request_id}")

            # Handle methods
            if method == "initialize":
                # MCP initialization
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {},
                        },
                        "serverInfo": {
                            "name": "asoba-mcp-server",
                            "version": "1.0.0",
                        },
                    },
                }
                _send_response(response)

            elif method == "tools/list":
                # List available tools
                tools = asoba_mcp_server.list_tools()
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": tools},
                }
                _send_response(response)

            elif method == "tools/call":
                # Execute a tool
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                logger.info(f"Calling tool: {tool_name}")

                result = await asoba_mcp_server.call_tool(tool_name, arguments)

                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2),
                            }
                        ],
                    },
                }
                _send_response(response)

            elif method == "ping":
                # Health check
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {},
                }
                _send_response(response)

            else:
                # Unknown method
                logger.warning(f"Unknown method: {method}")
                _send_error(request_id, -32601, f"Method not found: {method}")

        except Exception as e:
            logger.exception("Unexpected error in main loop")
            _send_error(None, -32603, f"Internal error: {e!s}")


def _send_response(response: dict):
    """Send JSON-RPC response to stdout."""
    print(json.dumps(response), flush=True)


def _send_error(request_id, code: int, message: str):
    """Send JSON-RPC error to stdout."""
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    print(json.dumps(response), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
