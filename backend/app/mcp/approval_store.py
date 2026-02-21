"""
MCP High-Risk Tool Approval Store (P8).

In-memory, single-use, 60-second TTL approval tokens tied to a
specific tool name. Prevents destructive tools from executing without
an explicit confirmation step.
"""

import logging
import uuid
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_APPROVAL_TTL_SECONDS = 60
_MAX_TOKENS = 500

# token -> (expires_at, tool_name)
_approval_tokens: dict[str, tuple[datetime, str]] = {}


def _cleanup_expired() -> None:
    """Remove expired tokens."""
    now = datetime.utcnow()
    expired = [t for t, (exp, _) in _approval_tokens.items() if now > exp]
    for t in expired:
        _approval_tokens.pop(t, None)


def create_approval_token(tool_name: str) -> str:
    """Create a single-use approval token for a high-risk tool.

    Args:
        tool_name: The tool this token authorizes.

    Returns:
        A UUID token string (valid for 60 seconds, single-use).
    """
    _cleanup_expired()

    if len(_approval_tokens) >= _MAX_TOKENS:
        sorted_tokens = sorted(_approval_tokens.items(), key=lambda x: x[1][0])
        for t, _ in sorted_tokens[: len(sorted_tokens) // 2]:
            _approval_tokens.pop(t, None)

    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(seconds=_APPROVAL_TTL_SECONDS)
    _approval_tokens[token] = (expires_at, tool_name)
    logger.info("Approval token created: tool=%s token=%s...%s", tool_name, token[:8], token[-4:])
    return token


def validate_approval_token(tool_name: str, token: str) -> bool:
    """Validate and consume a single-use approval token.

    Args:
        tool_name: The tool being called (must match the token's tool).
        token: The approval token to validate.

    Returns:
        True if valid, False if invalid/expired/wrong-tool/already-used.
    """
    _cleanup_expired()

    entry = _approval_tokens.pop(token, None)  # Remove immediately (single-use)
    if entry is None:
        return False

    expires_at, authorized_tool = entry
    if datetime.utcnow() > expires_at:
        return False
    if authorized_tool != tool_name:
        logger.warning(
            "Approval token tool mismatch: expected=%s got=%s",
            authorized_tool,
            tool_name,
        )
        return False

    return True


def reset_approval_store() -> None:
    """Clear all tokens. Used in tests."""
    _approval_tokens.clear()
