"""
MCP Tools Registry

Central registry for all MCP tools across domain modules.
Provides a unified interface for tool discovery and invocation.

Pattern:
1. Each domain module (core, operations, etc.) defines its tools
2. Each module exports a register_tools() function
3. Registry aggregates all tools and handlers
4. SIMBIOTMCPServer uses registry to initialize

Usage:
    from app.mcp.tools.registry import get_all_tools, get_all_handlers

    tools = get_all_tools()  # List of tool definitions
    handlers = get_all_handlers()  # Dict of tool_name -> async handler
"""

from typing import Dict, List, Any, Callable

# Placeholder for now - will import from individual modules when created
# from app.mcp.tools.core import get_core_tools, get_core_handlers
# from app.mcp.tools.operations import get_operations_tools, get_operations_handlers
# from app.mcp.tools.commercial import get_commercial_tools, get_commercial_handlers
# from app.mcp.tools.onboarding import get_onboarding_tools, get_onboarding_handlers
# from app.mcp.tools.ai import get_ai_tools, get_ai_handlers
# from app.mcp.tools.solar import get_solar_tools, get_solar_handlers


def get_all_tools() -> List[Dict[str, Any]]:
    """
    Get all MCP tool definitions.

    Returns:
        List of tool metadata dicts with name, description, and input schema
    """
    # TODO: Aggregate from all domain modules
    # tools = []
    # tools.extend(get_core_tools())
    # tools.extend(get_operations_tools())
    # tools.extend(get_commercial_tools())
    # tools.extend(get_onboarding_tools())
    # tools.extend(get_ai_tools())
    # tools.extend(get_solar_tools())
    # return tools

    # For now, return empty (original server keeps all tools in simbiot_server.py)
    return []


def get_all_handlers() -> Dict[str, Callable]:
    """
    Get all MCP tool handlers (mapping tool_name -> async function).

    Returns:
        Dict of {tool_name: async_handler_function}
    """
    # TODO: Aggregate from all domain modules
    # handlers = {}
    # handlers.update(get_core_handlers())
    # handlers.update(get_operations_handlers())
    # handlers.update(get_commercial_handlers())
    # handlers.update(get_onboarding_handlers())
    # handlers.update(get_ai_handlers())
    # handlers.update(get_solar_handlers())
    # return handlers

    # For now, return empty (original server keeps all handlers in simbiot_server.py)
    return {}
