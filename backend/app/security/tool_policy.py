"""
Tool Authorization Policy.

Enforces per-tool security policies:
    - Which roles can invoke which tools
    - Argument validation beyond JSON schema (e.g., site_id scoping)
    - Rate limiting per tool per user
    - Step-up auth requirements for destructive tools
    - Tool result context size limits (MAX_TOOL_RESULT_CONTEXT_SIZE)

Integrates with the existing role/module gating in chat_tools.py
and auth_middleware.py.
"""
