"""
calm_harness.py — Sanitizes tool errors before they reach LLM context.
Raw exceptions trigger panic vectors. Neutral messages do not.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(StrEnum):
    UNREACHABLE = "device_unreachable"
    TIMEOUT = "request_timeout"
    AUTH = "auth_failure"
    VALIDATION = "validation_failed"
    NOT_FOUND = "resource_not_found"
    PARSE = "parse_failed"
    UNAVAILABLE = "service_unavailable"
    UNKNOWN = "operation_failed"


_NEUTRAL_MESSAGES: dict[ErrorCategory, str] = {
    ErrorCategory.UNREACHABLE: "Device unreachable. Check connection and retry.",
    ErrorCategory.TIMEOUT: "Request timed out. The service may be busy.",
    ErrorCategory.AUTH: "Authentication failed. Credentials may need renewal.",
    ErrorCategory.VALIDATION: "Validation failed. Check input format.",
    ErrorCategory.NOT_FOUND: "Resource not found.",
    ErrorCategory.PARSE: "Could not parse response. Data may be malformed.",
    ErrorCategory.UNAVAILABLE: "Service temporarily unavailable.",
    ErrorCategory.UNKNOWN: "Operation failed. Try again or use an alternative approach.",
}

# Map exception types → category. Order matters — more specific first.
_EXCEPTION_MAP: list[tuple[type[Exception], ErrorCategory]] = [
    (ConnectionError, ErrorCategory.UNREACHABLE),
    (TimeoutError, ErrorCategory.TIMEOUT),
    (PermissionError, ErrorCategory.AUTH),
    (FileNotFoundError, ErrorCategory.NOT_FOUND),
    (ValueError, ErrorCategory.VALIDATION),
    (TypeError, ErrorCategory.VALIDATION),
    (UnicodeDecodeError, ErrorCategory.PARSE),
    (KeyError, ErrorCategory.PARSE),
]

# Lazy-import exception classes by name to avoid hard deps
_NAME_MAP: dict[str, ErrorCategory] = {
    "ConnectionError": ErrorCategory.UNREACHABLE,
    "ConnectionRefusedError": ErrorCategory.UNREACHABLE,
    "ConnectTimeout": ErrorCategory.TIMEOUT,
    "ReadTimeout": ErrorCategory.TIMEOUT,
    "Timeout": ErrorCategory.TIMEOUT,
    "HTTPError": ErrorCategory.UNAVAILABLE,
    "RequestException": ErrorCategory.UNAVAILABLE,
    "APIStatusError": ErrorCategory.UNAVAILABLE,
    "AuthenticationError": ErrorCategory.AUTH,
    "NotFoundError": ErrorCategory.NOT_FOUND,
    "ValidationError": ErrorCategory.VALIDATION,
    "JSONDecodeError": ErrorCategory.PARSE,
}


def categorise(exc: Exception) -> ErrorCategory:
    """Classify an exception into a calm ErrorCategory."""
    # Check class name first (catches library-specific exceptions without importing them)
    cls_name = type(exc).__name__
    if cls_name in _NAME_MAP:
        return _NAME_MAP[cls_name]
    # Walk MRO
    for exc_type, category in _EXCEPTION_MAP:
        if isinstance(exc, exc_type):
            return category
    return ErrorCategory.UNKNOWN


def calm_error(exc: Exception, tool_name: str = "tool") -> dict[str, Any]:
    """
    Convert a raw exception into a calm, LLM-safe tool result dict.

    Never surfaces exception messages, tracebacks, or class names to the LLM.
    Logs the real error at DEBUG level for diagnostics.

    Returns the standard SENTINEL tool result shape:
        {"status": "error", "message": str, "error_category": str, "tool": str}
    """
    category = categorise(exc)
    neutral_msg = _NEUTRAL_MESSAGES[category]

    # Real error goes to logs only — never to LLM
    logger.debug(
        "Tool error suppressed for LLM: tool=%s category=%s exc_type=%s exc=%s",
        tool_name,
        category.value,
        type(exc).__name__,
        exc,
        exc_info=False,
    )

    return {
        "status": "error",
        "message": neutral_msg,
        "error_category": category.value,
        "tool": tool_name,
    }


def calm_tool_result(data: Any, tool_name: str = "tool") -> dict[str, Any]:
    """Wrap a successful tool result in the standard shape."""
    return {
        "status": "success",
        "data": data,
        "tool": tool_name,
    }


# Calm harness — forced pause scratchpad for interactive/recommendation calls.
# Appended to system prompt when in interactive mode to prevent impulsive outputs.
SCRATCHPAD_PREFIX = """
Before writing your response, complete these steps:
1. List the affected equipment IDs and their current confidence levels.
2. Confirm the action is within current phase constraints — supervised mode requires human approval before execution.
3. Flag any tool results that were unavailable or incomplete — do not infer from silence.
4. Then write your recommendation.
"""


def calm_error_legacy(exc: Exception, tool_name: str = "tool") -> dict[str, Any]:
    """
    Same as calm_error but returns the legacy SENTINEL tool result shape:
    {"success": False, "error": str, "tool": str}

    Use this when replacing existing str(e) returns in code that already
    returns {"success": False, "error": ...} — keeps backward compatibility.
    """
    category = categorise(exc)
    neutral_msg = _NEUTRAL_MESSAGES[category]

    logger.debug(
        "Tool error suppressed for LLM: tool=%s category=%s exc_type=%s exc=%s",
        tool_name,
        category.value,
        type(exc).__name__,
        exc,
        exc_info=False,
    )

    return {
        "success": False,
        "error": neutral_msg,
        "tool": tool_name,
        "error_category": category.value,
    }
