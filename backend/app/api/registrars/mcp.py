"""MCP (Model Context Protocol) API router registrar.

Registers routers for MCP server integrations with AI systems.
"""

from fastapi import FastAPI

from app.api import mcp, mcp_sse, mcp_openai


def register_mcp_routers(app: FastAPI) -> None:
    """Register MCP API routers."""
    # MCP (Model Context Protocol) for AI tool integration
    app.include_router(mcp.router, tags=["mcp"])

    # MCP SSE transport for remote clients
    app.include_router(mcp_sse.router, tags=["mcp-sse"])

    # MCP OpenAI ChatGPT connector
    app.include_router(mcp_openai.router, tags=["mcp-openai"])
    app.include_router(mcp_openai.wellknown_router, tags=["mcp-discovery"])
