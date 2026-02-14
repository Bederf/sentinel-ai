"""Interfaces to prevent circular imports in AI services.

This module documents the contracts between AI services to maintain
loose coupling and prevent circular import dependencies.

Current Import Flow (no circular dependencies):
    ai_optimizer → claude_service → chat_tools

Architecture Rules:
    - chat_tools: Provides tool functions, NO dependencies on AI providers
    - claude_service: Uses chat_tools, implements chat provider
    - ai_optimizer: Uses claude_service for AI recommendations
    - hybrid_ai_service: Routes between Claude and Ollama

To prevent circular imports:
    1. Never import ai_optimizer from chat_tools or claude_service
    2. Never import claude_service from chat_tools
    3. Use runtime imports (inside functions) if cross-service calls are needed
    4. Depend on protocols/interfaces, not concrete implementations
"""

from typing import Dict, Any, List, Optional


# Document the expected contracts (for documentation purposes)

async def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    site_id: Optional[str] = None,
    user_email: Optional[str] = None,
    user_role: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a tool function (from chat_tools module).

    This is the contract that chat_tools.execute_tool provides.
    Import at runtime if needed from claude_service.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        Tool execution result
    """
    # Runtime import to prevent circular dependency
    from app.services.chat_tools import execute_tool as _execute_tool
    return await _execute_tool(
        tool_name,
        tool_input,
        site_id=site_id,
        user_email=user_email,
        user_role=user_role,
    )


def get_chat_tools(
    site_id: Optional[str] = None,
    user_email: Optional[str] = None,
    user_role: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get available chat tools (from chat_tools module).

    This is the contract that chat_tools.CHAT_TOOLS provides.
    Import at runtime if needed from claude_service.

    Returns:
        List of tool definitions with name, description, input_schema
    """
    # Runtime import to prevent circular dependency
    from app.services.chat_tools import get_chat_tools as _get_chat_tools
    return _get_chat_tools(site_id, user_email=user_email, user_role=user_role)


# Type aliases for better code documentation
ToolHandler = Any  # Callable that takes **kwargs and returns Dict[str, Any]
ToolDefinition = Dict[str, Any]  # Has name, description, input_schema
