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

# Import modular tool domains as they become available
from app.mcp.tools.code import get_code_tools, get_code_handlers


def get_all_tools() -> List[Dict[str, Any]]:
    """
    Get all MCP tool definitions.

    Returns:
        List of tool metadata dicts with name, description, and input schema
    """
    tools = []

    # Code search and fetch tools
    tools.extend(get_code_tools())

    # TODO: Add other domain tools as they're modularized
    # tools.extend(get_core_tools())
    # tools.extend(get_operations_tools())
    # tools.extend(get_commercial_tools())
    # tools.extend(get_onboarding_tools())
    # tools.extend(get_ai_tools())
    # tools.extend(get_solar_tools())

    return tools


def get_all_handlers() -> Dict[str, Callable]:
    """
    Get all MCP tool handlers (mapping tool_name -> async function).

    Returns:
        Dict of {tool_name: async_handler_function}
    """
    handlers = {}

    # Code search and fetch handlers
    handlers.update(get_code_handlers())

    # TODO: Add other domain handlers as they're modularized
    # handlers.update(get_core_handlers())
    # handlers.update(get_operations_handlers())
    # handlers.update(get_commercial_handlers())
    # handlers.update(get_onboarding_handlers())
    # handlers.update(get_ai_handlers())
    # handlers.update(get_solar_handlers())

    return handlers
