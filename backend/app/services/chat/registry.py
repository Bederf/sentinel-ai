"""
Chat Tools Registry

Central registry for all chat tool handlers.
Provides unified interface for tool discovery and execution.

Pattern:
1. Each domain module defines tool handler functions
2. Each module exports its handlers dict
3. Registry aggregates all handlers
4. Chat service uses registry for tool execution

Usage:
    from app.services.chat.registry import get_all_handlers, execute_tool

    handlers = get_all_handlers()  # Dict of tool_name -> async handler
    result = await execute_tool("list_devices")  # Execute by name
"""

import logging
from typing import Any, Dict, Callable

logger = logging.getLogger(__name__)

# Placeholder - will import from domain modules when split
# from app.services.chat.device import TOOL_HANDLERS as DEVICE_HANDLERS
# from app.services.chat.system import TOOL_HANDLERS as SYSTEM_HANDLERS
# from app.services.chat.analysis import TOOL_HANDLERS as ANALYSIS_HANDLERS
# from app.services.chat.niagara import TOOL_HANDLERS as NIAGARA_HANDLERS
# from app.services.chat.solar import TOOL_HANDLERS as SOLAR_HANDLERS
# from app.services.chat.security import TOOL_HANDLERS as SECURITY_HANDLERS


def get_all_handlers() -> Dict[str, Callable]:
    """
    Get all chat tool handlers.

    Returns:
        Dict mapping tool_name to async handler function
    """
    # TODO: Aggregate from all domain modules
    # handlers = {}
    # handlers.update(DEVICE_HANDLERS)
    # handlers.update(SYSTEM_HANDLERS)
    # handlers.update(ANALYSIS_HANDLERS)
    # handlers.update(NIAGARA_HANDLERS)
    # handlers.update(SOLAR_HANDLERS)
    # handlers.update(SECURITY_HANDLERS)
    # return handlers

    # For now, return empty (original chat_tools.py keeps all handlers)
    return {}


async def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a chat tool by name.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        Tool execution result

    Raises:
        ValueError: If tool not found
    """
    handlers = get_all_handlers()
    handler = handlers.get(tool_name)

    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return await handler(**tool_input)
    except TypeError as e:
        return {"error": f"Invalid parameters for {tool_name}: {e}"}
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return {"error": str(e)}
