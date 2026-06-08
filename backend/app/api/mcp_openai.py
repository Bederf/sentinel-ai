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

import hmac
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, Request
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


def as_single_text_content(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Format response as exactly one text content item with JSON-encoded string.

    This is the strict format required by OpenAI connectors:
    {
        "content": [
            {"type": "text", "text": "{...json string...}"}
        ]
    }
    """
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def as_single_text_error(error_message: str) -> dict[str, Any]:
    """Format error as single text content item."""
    return {"content": [{"type": "text", "text": json.dumps({"error": error_message})}], "isError": True}


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

    async def handle_initialize(self, params: dict) -> dict:
        """Handle MCP initialize request."""
        client_info = params.get("clientInfo", {})
        logger.info(f"MCP Initialize: {client_info.get('name', 'unknown')} v{client_info.get('version', '?')}")

        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "sentinel-bms-connector", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        }

    async def handle_tools_list(self) -> dict:
        """List available tools."""
        tools = self.server.list_tools()
        logger.debug(f"MCP tools/list: returning {len(tools)} tools")
        return {"tools": tools}

    async def handle_tools_call(self, params: dict) -> dict:
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
            return as_single_text_error(f"Internal error: {e!s}")

    async def handle_request(self, request_body: dict) -> dict:
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
                return {"jsonrpc": "2.0", "id": request_id, "result": {}}

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
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        except Exception as e:
            logger.error(f"MCP request error: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": f"Internal error: {e!s}"},
            }


# Singleton handler
_mcp_handler: MCPStreamableHTTPHandler | None = None


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
    authorization: str | None = Header(default=None, alias="Authorization"),
    accept: str | None = Header(default="application/json"),
):
    """
    Streamable HTTP MCP endpoint.

    Requires Authorization: Bearer header for authentication.
    Returns 401 if key is missing or invalid.

    This is the PRIMARY endpoint for:
    - ChatGPT Deep Research connectors
    - Microsoft 365 Copilot declarative agents

    URL: POST https://your-domain.com/api/mcp/openai/mcp

    Accepts:
    - Content-Type: application/json
    - Accept: application/json, text/event-stream
    - Authorization: Bearer <api-key>

    Test with:
        curl -X POST https://your-domain.com/api/mcp/openai/mcp \\
          -H "Content-Type: application/json" \\
          -H "Accept: application/json, text/event-stream" \\
          -H "X-API-Key: <your-api-key>" \\
          -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    """
    # Auth check
    from app.config.settings import settings

    expected_key = getattr(settings, "mcp_api_key", None) or getattr(settings, "MCP_API_KEY", None)
    if not expected_key:
        logger.error("MCP API key not configured — endpoint is open (auth disabled)")
    elif not authorization:
        logger.warning("MCP request missing Authorization header")
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32001, "message": "Missing Authorization: Bearer header — authentication required"},
            },
            headers=CORS_HEADERS,
        )
    else:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            logger.warning(f"MCP request with invalid auth scheme: {scheme}")
            return JSONResponse(
                status_code=401,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32001, "message": "Authorization must be: Bearer <api-key>"},
                },
                headers=CORS_HEADERS,
            )
        if not hmac.compare_digest(token.encode(), expected_key.encode()):
            logger.warning(f"MCP request with invalid API key: {token[:8]}...")
            return JSONResponse(
                status_code=401,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32001, "message": "Invalid API key"},
                },
                headers=CORS_HEADERS,
            )

    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"MCP invalid JSON: {e}")
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error: Invalid JSON"}},
            headers=CORS_HEADERS,
        )

    handler = get_mcp_handler()
    response = await handler.handle_request(body)

    return JSONResponse(content=response, headers=CORS_HEADERS)


@router.options("/mcp")
async def mcp_options():
    """Handle CORS preflight for MCP endpoint."""
    return Response(
        status_code=200,
        headers={
            **CORS_HEADERS,
            "Access-Control-Max-Age": "86400",
        },
    )


@router.get("/mcp")
async def mcp_get_info():
    """
    GET on MCP endpoint returns server info.

    Useful for connector discovery and health checks.
    """
    server = get_openai_connector_server()
    server._ensure_index()
    return JSONResponse(
        content={
            "name": "sentinel-bms-connector",
            "version": "1.0.0",
            "description": "SENTINEL BMS Intelligence Platform - Building Management Data Connector",
            "protocol": "MCP",
            "protocolVersion": "2024-11-05",
            "transport": "streamable-http",
            "tools": [t["name"] for t in server.list_tools()],
            "documents_indexed": len(server._documents),
        },
        headers=CORS_HEADERS,
    )


# =============================================================================
# Health & Info Endpoints
# =============================================================================


@router.get("/info")
async def openai_connector_info():
    """Get connector information and available tools."""
    server = get_openai_connector_server()
    server._ensure_index()
    tool_schemas = server.list_tools()
    return JSONResponse(
        content={
            "name": "sentinel-bms-connector",
            "version": "1.0.0",
            "description": "SENTINEL BMS Intelligence Platform - Building Management Data Connector",
            "mcp_version": "2024-11-05",
            "transport": "streamable-http",
            "mcp_endpoint": "/api/mcp/openai/mcp",
            "tools": tool_schemas,
            "capabilities": {t["name"]: t["description"] for t in tool_schemas},
        },
        headers=CORS_HEADERS,
    )


@router.get("/health")
async def openai_connector_health():
    """Health check endpoint - publicly accessible for external connectivity tests."""
    server = get_openai_connector_server()
    server._ensure_index()

    return JSONResponse(
        content={
            "status": "healthy",
            "documents_indexed": len(server._documents),
            "timestamp": datetime.now().isoformat(),
            "mcp_endpoint": "/api/mcp/openai/mcp",
            "transport": "streamable-http",
            "tools": [t["name"] for t in server.list_tools()],
        },
        headers=CORS_HEADERS,
    )


@router.get("/stats")
async def openai_connector_stats():
    """Get detailed index statistics."""
    server = get_openai_connector_server()
    return JSONResponse(content=server.get_stats(), headers=CORS_HEADERS)


@router.post("/refresh", include_in_schema=False)
async def openai_connector_refresh(authorization: str | None = Header(default=None, alias="Authorization")):
    """Force refresh the document index. Requires Bearer auth."""
    ok, err = _require_bearer_auth(authorization)
    if not ok:
        return err
    server = get_openai_connector_server()
    server.refresh_index()
    return JSONResponse(content={"status": "refreshed", "stats": server.get_stats()}, headers=CORS_HEADERS)


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
            "documentation": "https://modelcontextprotocol.io/specification/2025-06-18/basic/transports",
        },
        headers=CORS_HEADERS,
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
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"}, headers=CORS_HEADERS)

    handler = get_mcp_handler()
    response = await handler.handle_request(body)

    return JSONResponse(content=response, headers=CORS_HEADERS)


@router.options("/sse")
@router.options("/sse/")
async def sse_options():
    """Handle CORS preflight for legacy SSE endpoint."""
    return Response(
        status_code=200,
        headers={
            **CORS_HEADERS,
            "Access-Control-Max-Age": "86400",
        },
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
    server = get_openai_connector_server()
    tool_schemas = server.list_tools()
    return JSONResponse(
        content={
            "name": "sentinel-bms-connector",
            "version": "1.0.0",
            "description": "SENTINEL BMS Intelligence Platform - Building Management Data Connector",
            "mcp": {"version": "2024-11-05", "transport": "streamable-http", "endpoint": "/api/mcp/openai/mcp"},
            "tools": [t["name"] for t in tool_schemas],
            "capabilities": {t["name"]: t["description"] for t in tool_schemas},
        },
        headers=CORS_HEADERS,
    )


@wellknown_router.options("/.well-known/mcp.json")
async def mcp_discovery_options():
    """Handle CORS preflight for MCP discovery endpoint."""
    return Response(
        status_code=200,
        headers={
            **CORS_HEADERS,
            "Access-Control-Max-Age": "86400",
        },
    )


# =============================================================================
# Well-Known OpenAPI Schema for ChatGPT Actions
# =============================================================================


@wellknown_router.get("/.well-known/openapi.json")
async def well_known_openapi():
    """
    OpenAPI 3.1 schema for ChatGPT Actions discovery.

    Dynamically generates path operations from live MCP tool definitions.
    Always stays in sync with actual tool availability — never hardcoded.
    """
    server = get_openai_connector_server()
    tool_schemas = server.list_tools()

    paths: dict[str, Any] = {}
    for tool in tool_schemas:
        tool_name = tool.get("name", "")
        tool_desc = tool.get("description", "")
        input_schema = tool.get("inputSchema", {}) or {}

        # Truncate description to first sentence for OpenAPI summary
        first_sentence = tool_desc.split(".")[0] if tool_desc else tool_name

        # Build request body schema from tool's inputSchema properties
        properties = {}
        required: list[str] = []
        schema_props = input_schema.get("properties", {})
        for prop_name, prop_def in schema_props.items():
            properties[prop_name] = {k: v for k, v in prop_def.items() if k != "description"}
            if prop_def.get("required"):
                required.append(prop_name)

        request_body_schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            request_body_schema["required"] = required

        paths[f"/{tool_name}"] = {
            "post": {
                "operationId": tool_name,
                "summary": first_sentence,
                "description": tool_desc,
                "tags": ["SENTINEL BMS"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": request_body_schema}},
                },
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        }

    logger.info(f"Well-known OpenAPI schema generated with {len(paths)} tool paths")

    return JSONResponse(
        content={
            "openapi": "3.1.0",
            "info": {
                "title": "SENTINEL BMS MCP",
                "version": "1.0.0",
                "description": "SENTINEL Building Management Intelligence — live operational data for S002 (Sandton City Office Tower). S001 (Fairlands) is in commissioning.",
            },
            "servers": [{"url": "https://bms.sentinel-ai.co.za/api/mcp/openai"}],
            "paths": paths,
        },
        headers=CORS_HEADERS,
    )


@wellknown_router.options("/.well-known/openapi.json")
async def well_known_openapi_options():
    """Handle CORS preflight for well-known OpenAPI endpoint."""
    return Response(
        status_code=200,
        headers={
            **CORS_HEADERS,
            "Access-Control-Max-Age": "86400",
        },
    )


@router.get("/openapi.json", include_in_schema=True)
async def openapi_json():
    """
    OpenAPI 3.1 schema for GPT Actions integration.

    GPT Actions requires an OpenAPI schema to describe tool endpoints.
    This endpoint returns a complete schema covering all MCP tools
    (ping, search, fetch, inspect_equipment, get_site_status, etc.)
    formatted as proper REST endpoints for GPT Actions consumption.

    Schema is auto-generated from MCP tool definitions.
    """
    from app.mcp.openai_connector_server import get_openai_connector_server

    server = get_openai_connector_server()
    tools = server.list_tools()

    paths: dict[str, Any] = {}

    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "") or f"SENTINEL tool: {name}"
        input_schema = tool.get("inputSchema", {}) or {}

        # Build requestBody from inputSchema
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        schema_body = {"type": "object"}
        if properties:
            schema_body["properties"] = {
                k: {**v, "description": v.get("description", "")} for k, v in properties.items()
            }
        if required:
            schema_body["required"] = required

        request_body_content = {"application/json": {"schema": schema_body}}

        paths[f"/{name}"] = {
            "post": {
                "operationId": name,
                "summary": desc[:160],
                "description": desc,
                "requestBody": {
                    "required": True,
                    "content": request_body_content,
                },
                "responses": {
                    "200": {
                        "description": f"{name} response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "content": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }

    logger.info(f"OpenAPI schema generated with {len(paths)} tool paths")

    return JSONResponse(
        content={
            "openapi": "3.1.0",
            "info": {
                "title": "SENTINEL BMS API",
                "version": "1.0.0",
                "description": "SENTINEL Building Management Intelligence Platform — live operational data for Sandton City Office Tower (site-002).",
            },
            "servers": [{"url": "https://bms.sentinel-ai.co.za/api/mcp/openai"}],
            "paths": paths,
            "components": {
                "schemas": {
                    "Error": {
                        "type": "object",
                        "properties": {"error": {"type": "string"}},
                    }
                }
            },
        },
        headers=CORS_HEADERS,
    )


# =============================================================================
# OpenAPI Tool Endpoints (for GPT Actions no-auth integration)
# =============================================================================


def _require_bearer_auth(authorization: str | None) -> tuple[bool, JSONResponse | None]:
    """Check Bearer auth. Returns (ok, error_response). If ok=True, caller proceeds."""
    from app.config.settings import settings

    expected_key = getattr(settings, "mcp_api_key", None) or getattr(settings, "MCP_API_KEY", None)
    if not expected_key:
        logger.error("MCP API key not configured — auth disabled")
        return True, None  # Allow when key not configured
    if not authorization:
        return False, JSONResponse(
            status_code=401,
            content={"error": "Missing Authorization: Bearer header"},
            headers=CORS_HEADERS,
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False, JSONResponse(
            status_code=401,
            content={"error": "Authorization must be: Bearer <api-key>"},
            headers=CORS_HEADERS,
        )
    if not hmac.compare_digest(token.encode(), expected_key.encode()):
        return False, JSONResponse(
            status_code=401,
            content={"error": "Invalid API key"},
            headers=CORS_HEADERS,
        )
    return True, None


async def _tool_endpoint(tool_name: str, request_data: dict | None, authorization: str | None = None) -> JSONResponse:
    """Generic handler for all OpenAPI tool endpoints. Requires Bearer auth."""
    ok, err = _require_bearer_auth(authorization)
    if not ok:
        return err
    server = get_openai_connector_server()
    try:
        result = await server.call_tool(tool_name, **(request_data or {}))
        return JSONResponse(content={"content": [{"type": "text", "text": json.dumps(result)}]}, headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"[{tool_name}] tool call failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True},
            headers=CORS_HEADERS,
        )


# =============================================================================
# OpenAPI Tool Endpoints (GPT Actions / no-auth MCP clients — requires Bearer auth)
# =============================================================================


def _tool_endpoint_with_auth(tool_name: str):
    """Decorator factory: creates auth-gated tool endpoint."""

    async def wrapper(request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
        body = await request.json() if request.body else {}
        return await _tool_endpoint(tool_name, body, authorization)

    return wrapper


@router.post("/search", include_in_schema=False)
async def tool_search(request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
    body = await request.json()
    return await _tool_endpoint("search", body, authorization)


@router.post("/fetch", include_in_schema=False)
async def tool_fetch(request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
    body = await request.json()
    return await _tool_endpoint("fetch", body, authorization)


@router.post("/get_site_status", include_in_schema=False)
async def tool_get_site_status(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_site_status", body, authorization)


@router.post("/get_recommendations", include_in_schema=False)
async def tool_get_recommendations(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_recommendations", body, authorization)


@router.post("/trace_recommendation", include_in_schema=False)
async def tool_trace_recommendation(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("trace_recommendation", body, authorization)


@router.post("/inspect_equipment", include_in_schema=False)
async def tool_inspect_equipment(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("inspect_equipment", body, authorization)


@router.post("/get_roi_summary", include_in_schema=False)
async def tool_get_roi_summary(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_roi_summary", body, authorization)


@router.post("/analyze_impact", include_in_schema=False)
async def tool_analyze_impact(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("analyze_impact", body, authorization)


@router.post("/compare_sites", include_in_schema=False)
async def tool_compare_sites(request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
    body = await request.json()
    return await _tool_endpoint("compare_sites", body, authorization)


@router.post("/get_curtailable_load", include_in_schema=False)
async def tool_get_curtailable_load(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_curtailable_load", body, authorization)


@router.post("/get_odse_export", include_in_schema=False)
async def tool_get_odse_export(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_odse_export", body, authorization)


@router.post("/search_knowledge", include_in_schema=False)
async def tool_search_knowledge(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("search_knowledge", body, authorization)


@router.post("/get_knowledge_detail", include_in_schema=False)
async def tool_get_knowledge_detail(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_knowledge_detail", body, authorization)


@router.post("/get_work_orders", include_in_schema=False)
async def tool_get_work_orders(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_work_orders", body, authorization)


@router.post("/get_work_order", include_in_schema=False)
async def tool_get_work_order(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_work_order", body, authorization)


@router.post("/ping", include_in_schema=False)
async def tool_ping(request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
    body = await request.json() if request.body else {}
    return await _tool_endpoint("ping", body, authorization)
