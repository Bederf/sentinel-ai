"""
Credential Scanner for Tool Inputs
====================================
Scans chat tool argument values for leaked credentials, API keys, tokens,
and connection strings BEFORE they are passed to tool handlers.

Reuses patterns from output_filter.py but applied to INPUTS.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Credential patterns — ordered by specificity (most specific first)
_CREDENTIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    # AWS access keys
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws_access_key"),
    # Anthropic API keys
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "anthropic_api_key"),
    # OpenAI API keys
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b"), "openai_api_key"),
    # Stripe keys
    (re.compile(r"\b(?:sk_test|sk_live|pk_test|pk_live)_[A-Za-z0-9]{20,}\b"), "stripe_key"),
    # Supabase service role keys (eyJ... JWT format, long)
    (re.compile(r"\beyJ[A-Za-z0-9_-]{50,}\.[A-Za-z0-9_-]{50,}\.[A-Za-z0-9_-]{20,}\b"), "jwt_token"),
    # Generic bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"), "bearer_token"),
    # Database connection strings with passwords
    (re.compile(r"(?:postgresql|postgres|mysql|mongodb|redis)://[^\s]+:[^\s@]+@[^\s]+"), "db_connection_string"),
    # Generic password-like assignments
    (
        re.compile(
            r"(?:password|passwd|pwd|secret|token)\s*[=:]\s*['\"]?[A-Za-z0-9!@#$%^&*_+-]{8,}['\"]?", re.IGNORECASE
        ),
        "password_assignment",
    ),
    # GitHub tokens
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"), "github_token"),
    # Telegram bot tokens
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "telegram_bot_token"),
]

# Fields to skip (internal/metadata fields)
_SKIP_FIELDS = {"site_id", "equipment_id", "equipment_code", "_user_email", "limit", "offset", "status", "priority"}


def scan_tool_input(tool_name: str, tool_input: dict) -> list[dict]:
    """Scan tool input arguments for credential patterns.

    Args:
        tool_name: Name of the tool being executed
        tool_input: Dict of arguments from Claude's tool_use

    Returns:
        List of findings: [{"field": str, "pattern": str, "snippet": str}]
        Empty list means clean input.
    """
    findings: list[dict] = []

    for key, value in tool_input.items():
        if key in _SKIP_FIELDS or key.startswith("_"):
            continue

        # Only scan string values > 10 chars
        text = _extract_text(value)
        if not text or len(text) < 10:
            continue

        for pattern, pattern_name in _CREDENTIAL_PATTERNS:
            match = pattern.search(text)
            if match:
                # Extract a safe snippet (redact most of the match)
                matched = match.group()
                snippet = matched[:6] + "..." + matched[-4:] if len(matched) > 12 else "***"

                findings.append(
                    {
                        "field": key,
                        "pattern": pattern_name,
                        "snippet": snippet,
                    }
                )
                break  # One finding per field is enough

    return findings


def redact_credentials(tool_input: dict) -> dict:
    """Return a copy of tool_input with detected credentials redacted.

    Does NOT modify the original dict.
    """
    clean = dict(tool_input)

    for key, value in clean.items():
        if key in _SKIP_FIELDS or key.startswith("_"):
            continue

        if isinstance(value, str) and len(value) >= 10:
            for pattern, pattern_name in _CREDENTIAL_PATTERNS:
                value = pattern.sub(f"[REDACTED-{pattern_name.upper()}]", value)
            clean[key] = value

    return clean


def _extract_text(value: Any) -> str:
    """Extract searchable text from a tool argument value."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Concatenate all string values
        parts = [str(v) for v in value.values() if isinstance(v, str)]
        return " ".join(parts)
    if isinstance(value, list):
        parts = [str(v) for v in value if isinstance(v, str)]
        return " ".join(parts)
    return ""
