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

_SITE_ID_CODE_CACHE: dict[str, str] = {}

TENANT_SCOPED_DEFAULT_TOOLS = {
    "search",
    "fetch",
    "ping",
    "get_site_status",
    "get_hvac_runtime_status",
    "get_recommendations",
    "inspect_equipment",
    "get_roi_summary",
    "get_curtailable_load",
    "get_odse_export",
    "search_knowledge",
    "get_knowledge_detail",
    "get_work_orders",
}


def _normalize_site_code(site_id: str | None) -> str:
    """Normalize S005/site-005/UUID-ish site input to the canonical site-### code."""
    if not site_id:
        return ""
    value = str(site_id).strip()
    if not value:
        return ""
    lower = value.lower()
    if lower.startswith("site-"):
        return lower
    upper = value.upper()
    if len(upper) == 4 and upper.startswith("S") and upper[1:].isdigit():
        return f"site-{upper[1:]}"
    if len(value) == 36 and value.count("-") == 4:
        cached = _SITE_ID_CODE_CACHE.get(value)
        if cached:
            return cached
        try:
            from app.database.supabase_client import get_supabase_client

            sb = get_supabase_client()
            result = sb.table("sites").select("code").eq("id", value).limit(1).execute()
            if result.data:
                code = str(result.data[0].get("code") or value).lower()
                _SITE_ID_CODE_CACHE[value] = code
                return code
        except Exception as exc:
            logger.warning("Could not resolve site UUID for MCP tenant filter: %s", exc)
    return lower


def _display_site_code(site_id: str) -> str:
    """Return the short S### form used by GPT Action schemas."""
    site_code = _normalize_site_code(site_id)
    if site_code.startswith("site-") and len(site_code) == 8:
        return f"S{site_code[-3:]}"
    return site_id


def _load_tenant_key_config() -> dict[str, dict[str, Any]]:
    """Parse MCP_TENANT_API_KEYS into token -> tenant context config."""
    from app.config.settings import settings

    raw = getattr(settings, "mcp_tenant_api_keys", "") or ""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Invalid MCP_TENANT_API_KEYS JSON; ignoring tenant-scoped keys")
        return {}
    if not isinstance(parsed, dict):
        logger.error("MCP_TENANT_API_KEYS must be a JSON object; ignoring tenant-scoped keys")
        return {}
    return {str(token): cfg for token, cfg in parsed.items() if isinstance(cfg, dict)}


def _auth_context_for_token(token: str) -> dict[str, Any] | None:
    """Return tenant auth context for a bearer token, preserving legacy S002 behavior."""
    from app.config.settings import settings

    legacy_key = getattr(settings, "mcp_api_key", None) or getattr(settings, "MCP_API_KEY", None)
    if legacy_key and hmac.compare_digest(token.encode(), legacy_key.encode()):
        return {
            "tenant_id": "legacy-s002",
            "allowed_sites": ["site-002"],
            "allowed_tools": set(TENANT_SCOPED_DEFAULT_TOOLS),
            "legacy": True,
        }

    for configured_token, cfg in _load_tenant_key_config().items():
        if not hmac.compare_digest(token.encode(), configured_token.encode()):
            continue
        allowed_sites = [_normalize_site_code(site) for site in cfg.get("allowed_sites", []) if site]
        tools = cfg.get("tools")
        allowed_tools = set(tools) if isinstance(tools, list) and tools else set(TENANT_SCOPED_DEFAULT_TOOLS)
        return {
            "tenant_id": str(cfg.get("tenant_id") or "tenant"),
            "allowed_sites": allowed_sites,
            "allowed_tools": allowed_tools,
            "legacy": False,
        }
    return None


def _is_authorized_for_tool(auth_ctx: dict[str, Any], tool_name: str, request_data: dict | None) -> tuple[bool, str]:
    """Enforce tenant tool and site scope before dispatching to MCP tool handlers."""
    allowed_tools = auth_ctx.get("allowed_tools")
    if allowed_tools is not None and tool_name not in allowed_tools:
        return False, f"Tool '{tool_name}' is not enabled for this tenant"

    allowed_sites = set(auth_ctx.get("allowed_sites") or [])
    if not allowed_sites:
        return True, ""

    request_data = request_data or {}
    requested_site = request_data.get("site_id")
    if requested_site:
        site_code = _normalize_site_code(str(requested_site))
        if site_code not in allowed_sites:
            return False, f"Tenant is not authorized for site_id '{requested_site}'"

    return True, ""


def _doc_is_allowed_for_tenant(auth_ctx: dict[str, Any] | None, doc: dict[str, Any] | None) -> bool:
    """Allow global technical docs, but scope Supabase operational records by site."""
    if not auth_ctx:
        return True
    allowed_sites = {_normalize_site_code(site) for site in (auth_ctx.get("allowed_sites") or []) if site}
    if not allowed_sites:
        return True
    if not doc:
        return False

    if doc.get("doc_type") == "technical_document" or doc.get("metadata", {}).get("scope") == "global":
        return True

    source = doc.get("metadata", {}).get("source")
    site_id = doc.get("metadata", {}).get("site_id")
    if source == "supabase" and not site_id:
        return False
    if site_id:
        return _normalize_site_code(str(site_id)) in allowed_sites
    return True


def _filter_result_for_tenant(
    auth_ctx: dict[str, Any] | None,
    tool_name: str,
    result: dict[str, Any],
    server: Any,
) -> dict[str, Any]:
    """Filter search/fetch document results without hiding global docs."""
    if not auth_ctx or tool_name not in {"search", "fetch"}:
        return result

    server._ensure_index()
    doc_index = getattr(server, "_document_index", {}) or {}

    if tool_name == "search":
        filtered_results = []
        for item in result.get("results", []):
            doc = doc_index.get(item.get("id"))
            if _doc_is_allowed_for_tenant(auth_ctx, doc):
                filtered_results.append(item)
        return {**result, "results": filtered_results}

    doc = doc_index.get(result.get("id"))
    if _doc_is_allowed_for_tenant(auth_ctx, doc):
        return result
    return {
        "id": result.get("id", ""),
        "title": "Document Not Found",
        "text": "No document found with that ID for this tenant.",
        "url": "",
        "metadata": {"error": "not_found"},
    }


def _tools_for_schema(tools: list[dict[str, Any]], site_id: str | None = None) -> list[dict[str, Any]]:
    """Build OpenAPI tool definitions for a site-scoped GPT schema."""
    if not site_id:
        return tools

    display_site = _display_site_code(site_id)
    filtered = []
    for tool in tools:
        if tool.get("name") not in TENANT_SCOPED_DEFAULT_TOOLS:
            continue
        cloned = json.loads(json.dumps(tool))
        properties = cloned.get("inputSchema", {}).get("properties", {})
        if "site_id" in properties:
            properties["site_id"]["enum"] = [display_site]
            properties["site_id"]["description"] = f"Site identifier for this tenant ({display_site})"
        filtered.append(cloned)
    return filtered


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

    async def handle_tools_list(self, auth_ctx: dict[str, Any] | None = None) -> dict:
        """List available tools."""
        tools = self.server.list_tools()
        if auth_ctx:
            allowed_tools = auth_ctx.get("allowed_tools") or TENANT_SCOPED_DEFAULT_TOOLS
            tools = [tool for tool in tools if tool.get("name") in allowed_tools]
            allowed_sites = auth_ctx.get("allowed_sites") or []
            if allowed_sites:
                tools = _tools_for_schema(tools, allowed_sites[0])
        logger.debug(f"MCP tools/list: returning {len(tools)} tools")
        return {"tools": tools}

    async def handle_tools_call(self, params: dict, auth_ctx: dict[str, Any] | None = None) -> dict:
        """
        Execute tool call with OpenAI connector response format.

        Returns exactly one content item of type text with JSON-encoded string.
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        logger.info(f"MCP tools/call: {tool_name}({json.dumps(arguments)[:100]})")

        try:
            if auth_ctx:
                allowed, reason = _is_authorized_for_tool(auth_ctx, tool_name, arguments)
                if not allowed:
                    raise ValueError(reason)
            result = await self.server.call_tool(tool_name, **arguments)
            result = _filter_result_for_tenant(auth_ctx, tool_name, result, self.server)
            return as_single_text_content(result)

        except ValueError as e:
            logger.warning(f"MCP tool error: {e}")
            return as_single_text_error(str(e))

        except Exception as e:
            logger.error(f"MCP internal error: {e}", exc_info=True)
            return as_single_text_error(f"Internal error: {e!s}")

    async def handle_request(self, request_body: dict, auth_ctx: dict[str, Any] | None = None) -> dict:
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
                result = await self.handle_tools_list(auth_ctx)

            elif method == "tools/call":
                result = await self.handle_tools_call(params, auth_ctx)

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
    tenant_keys = _load_tenant_key_config()
    auth_ctx: dict[str, Any] | None = None
    if not expected_key and not tenant_keys:
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
        auth_ctx = _auth_context_for_token(token)
        if auth_ctx is None:
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
    response = await handler.handle_request(body, auth_ctx)

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
    ok, err, _auth_ctx = _require_bearer_auth(authorization)
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
async def well_known_openapi(site_id: str | None = None):
    """
    OpenAPI 3.1 schema for ChatGPT Actions discovery.

    Dynamically generates path operations from live MCP tool definitions.
    Always stays in sync with actual tool availability — never hardcoded.
    """
    server = get_openai_connector_server()
    tool_schemas = _tools_for_schema(server.list_tools(), site_id)

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
                "description": (
                    "SENTINEL Building Management Intelligence — "
                    "live operational data for S002 (Sandton City Office Tower). "
                    "S001 (Fairlands) is in commissioning."
                ),
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
async def openapi_json(site_id: str | None = None):
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
    tools = _tools_for_schema(server.list_tools(), site_id)

    paths: dict[str, Any] = {}

    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "") or f"SENTINEL tool: {name}"
        input_schema = tool.get("inputSchema", {}) or {}

        # Build requestBody from inputSchema
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        schema_body = {
            "type": "object",
            "properties": {k: {**v, "description": v.get("description", "")} for k, v in properties.items()},
        }
        if not properties:
            schema_body["properties"] = {}
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
                "description": (
                    "SENTINEL Building Management Intelligence Platform — "
                    + (
                        f"tenant-scoped operational data for {_normalize_site_code(site_id)}."
                        if site_id
                        else "live operational data for Sandton City Office Tower (site-002)."
                    )
                ),
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


def _require_bearer_auth(authorization: str | None) -> tuple[bool, JSONResponse | None, dict[str, Any] | None]:
    """Check Bearer auth. Returns (ok, error_response, auth_context)."""
    from app.config.settings import settings

    expected_key = getattr(settings, "mcp_api_key", None) or getattr(settings, "MCP_API_KEY", None)
    tenant_keys = _load_tenant_key_config()
    if not expected_key and not tenant_keys:
        logger.error("MCP API key not configured — auth disabled")
        return True, None, None  # Allow when key not configured
    if not authorization:
        return (
            False,
            JSONResponse(
                status_code=401,
                content={"error": "Missing Authorization: Bearer header"},
                headers=CORS_HEADERS,
            ),
            None,
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return (
            False,
            JSONResponse(
                status_code=401,
                content={"error": "Authorization must be: Bearer <api-key>"},
                headers=CORS_HEADERS,
            ),
            None,
        )
    auth_ctx = _auth_context_for_token(token)
    if auth_ctx is None:
        return (
            False,
            JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"},
                headers=CORS_HEADERS,
            ),
            None,
        )
    return True, None, auth_ctx


async def _tool_endpoint(tool_name: str, request_data: dict | None, authorization: str | None = None) -> JSONResponse:
    """Generic handler for all OpenAPI tool endpoints. Requires Bearer auth."""
    ok, err, auth_ctx = _require_bearer_auth(authorization)
    if not ok:
        return err
    if auth_ctx:
        allowed, reason = _is_authorized_for_tool(auth_ctx, tool_name, request_data)
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"content": [{"type": "text", "text": json.dumps({"error": reason})}], "isError": True},
                headers=CORS_HEADERS,
            )
    server = get_openai_connector_server()
    try:
        result = await server.call_tool(tool_name, **(request_data or {}))
        result = _filter_result_for_tenant(auth_ctx, tool_name, result, server)
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


@router.post("/get_hvac_runtime_status", include_in_schema=False)
async def tool_get_hvac_runtime_status(
    request: Request, authorization: str | None = Header(default=None, alias="Authorization")
):
    body = await request.json()
    return await _tool_endpoint("get_hvac_runtime_status", body, authorization)


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
