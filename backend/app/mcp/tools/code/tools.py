"""
Code Search & Fetch MCP Tools

Provides tools for searching and fetching source code from the local codebase.
Tools are registered with the MCP server and callable via the standard MCP interface.
"""

from typing import Any, Dict, List
import logging

from .search import (
    search_files_by_pattern,
    search_file_contents,
    search_symbols,
    build_directory_tree,
    fetch_file_content,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Definitions (MCP Format)
# =============================================================================

TOOLS = [
    {
        "name": "code_search",
        "description": (
            "Search for files and code in the codebase. Supports glob patterns, content search, and symbol search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query: file pattern (e.g., '*.tsx', 'components/**/*.py'), keyword, or symbol name"
                    ),
                },
                "search_type": {
                    "type": "string",
                    "enum": ["file", "content", "symbol"],
                    "description": (
                        "Type of search: 'file' for glob patterns, "
                        "'content' for keyword/regex, "
                        "'symbol' for function/class names"
                    ),
                },
                "base_path": {
                    "type": "string",
                    "description": "Optional subdirectory to search in (e.g., 'frontend/src', 'backend/app')",
                },
                "is_regex": {
                    "type": "boolean",
                    "description": "If true and search_type='content', treat query as regex pattern",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 50 for files, 20 for content)",
                },
            },
            "required": ["query", "search_type"],
        },
    },
    {
        "name": "code_fetch",
        "description": "Fetch full content of a specific file by its path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path to file from codebase root (e.g., 'frontend/src/components/Dashboard.tsx')"
                    ),
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "code_structure",
        "description": "Get directory tree structure and architectural overview of codebase.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional subdirectory to explore (e.g., 'frontend/src', 'backend')",
                },
                "depth": {"type": "integer", "description": "Maximum directory depth to traverse (default: 2)"},
                "exclude_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns to exclude (e.g., ['*.log', '__pycache__'])",
                },
            },
        },
    },
]


# =============================================================================
# Tool Handler Functions
# =============================================================================


async def code_search(**kwargs) -> Dict[str, Any]:
    """
    Handler for code_search tool.

    Searches for files and code based on query and search type.
    """
    query = kwargs.get("query")
    search_type = kwargs.get("search_type")
    base_path = kwargs.get("base_path")
    is_regex = kwargs.get("is_regex", False)
    limit = kwargs.get("limit")

    if not query:
        return {"error": "query parameter is required"}
    if not search_type:
        return {"error": "search_type parameter is required"}

    if search_type not in ["file", "content", "symbol"]:
        return {"error": f"Invalid search_type: {search_type}. Must be 'file', 'content', or 'symbol'"}

    try:
        if search_type == "file":
            results = search_files_by_pattern(pattern=query, base_path=base_path, limit=limit or 50)
            return {
                "search_type": "file",
                "query": query,
                "base_path": base_path or "root",
                "result_count": len(results),
                "results": results,
            }

        elif search_type == "content":
            results = search_file_contents(query=query, base_path=base_path, is_regex=is_regex, limit=limit or 20)
            return {
                "search_type": "content",
                "query": query,
                "is_regex": is_regex,
                "base_path": base_path or "root",
                "result_count": len(results),
                "results": results,
            }

        elif search_type == "symbol":
            results = search_symbols(symbol_name=query, base_path=base_path)
            return {
                "search_type": "symbol",
                "query": query,
                "base_path": base_path or "root",
                "result_count": len(results),
                "results": results,
            }

    except Exception as e:
        logger.error(f"code_search error: {e}", exc_info=True)
        return {"error": f"Search failed: {str(e)}"}


async def code_fetch(**kwargs) -> Dict[str, Any]:
    """
    Handler for code_fetch tool.

    Fetches full content of a specific file.
    """
    path = kwargs.get("path")

    if not path:
        return {"error": "path parameter is required"}

    try:
        result = fetch_file_content(path)
        return result
    except Exception as e:
        logger.error(f"code_fetch error: {e}", exc_info=True)
        return {"error": f"Fetch failed: {str(e)}"}


async def code_structure(**kwargs) -> Dict[str, Any]:
    """
    Handler for code_structure tool.

    Returns directory tree and architectural overview.
    """
    path = kwargs.get("path")
    depth = kwargs.get("depth", 2)
    exclude_patterns = kwargs.get("exclude_patterns")

    try:
        result = build_directory_tree(base_path=path, depth=depth, exclude_patterns=exclude_patterns)
        return result
    except Exception as e:
        logger.error(f"code_structure error: {e}", exc_info=True)
        return {"error": f"Structure retrieval failed: {str(e)}"}


# =============================================================================
# Registry Functions
# =============================================================================


def get_code_tools() -> List[Dict[str, Any]]:
    """
    Get code tool definitions for MCP registration.

    Returns:
        List of tool metadata dicts with name, description, and input schema
    """
    return TOOLS


def get_code_handlers() -> Dict[str, Any]:
    """
    Get code tool handlers for MCP invocation.

    Returns:
        Dict mapping tool_name to async handler function
    """
    return {
        "code_search": code_search,
        "code_fetch": code_fetch,
        "code_structure": code_structure,
    }
