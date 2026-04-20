"""
Code Search & Fetch Tools for MCP

Provides tools for searching and fetching source code from the local codebase.

Tools:
  - code_search: Search for files by name/pattern or content keyword
  - code_fetch: Get full file contents by path
  - code_structure: Get directory tree and architectural overview
"""

from .tools import (
    get_code_handlers,
    get_code_tools,
)

__all__ = [
    "get_code_handlers",
    "get_code_tools",
]
