"""
MCP Tool Input/Output Validation (P3) and Secret-Zero Output Filter.

Validates tool arguments against JSON schemas defined in MCP_TOOLS,
enforces size limits on both inputs and outputs, and scans outputs
for credential-like fields that must never reach the model path.
"""

import json
import logging
import re
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# Keys in tool output that indicate credential leakage
_SECRET_OUTPUT_KEYS: set[str] = {
    "api_key",
    "apikey",
    "api_secret",
    "authorization",
    "access_token",
    "refresh_token",
    "secret_key",
    "private_key",
    "password",
    "credential",
    "token",
    "jwt",
    "bearer",
    "client_secret",
    "auth_token",
    "session_token",
}

# Patterns that look like secrets in string values
_SECRET_VALUE_PATTERNS = [
    re.compile(r"^(?:sk|pk|sent_sk)(?:_(?:test|live))?_[A-Za-z0-9]{20,}$"),  # API key patterns
    re.compile(r"^Bearer\s+[A-Za-z0-9._-]{20,}$"),  # Bearer tokens
    re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT tokens
]

MAX_STRING_LENGTH = 10_000  # Per-field string limit
MAX_ARRAY_ITEMS = 1_000  # Per-field array limit
MAX_OUTPUT_SIZE_BYTES = 500_000  # 500KB output cap


def _check_sizes(value: Any, path: str = "") -> str | None:
    """Recursively check string/array sizes. Returns error message or None."""
    if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
        return f"Field '{path}' exceeds max string length ({len(value)} > {MAX_STRING_LENGTH})"
    if isinstance(value, list):
        if len(value) > MAX_ARRAY_ITEMS:
            return f"Field '{path}' exceeds max array items ({len(value)} > {MAX_ARRAY_ITEMS})"
        for i, item in enumerate(value):
            err = _check_sizes(item, f"{path}[{i}]")
            if err:
                return err
    if isinstance(value, dict):
        for k, v in value.items():
            err = _check_sizes(v, f"{path}.{k}" if path else k)
            if err:
                return err
    return None


def validate_tool_input(
    tool_name: str,
    arguments: dict,
    schema: dict,
) -> tuple[bool, str | None]:
    """Validate args against JSON schema + size limits.

    Args:
        tool_name: Name of the tool being called.
        arguments: The arguments dict to validate.
        schema: The JSON schema (``input_schema`` from MCP_TOOLS).

    Returns:
        ``(True, None)`` on success, ``(False, error_message)`` on failure.
    """
    # 1. Recursive size check
    size_err = _check_sizes(arguments)
    if size_err:
        logger.warning("MCP input size violation: tool=%s %s", tool_name, size_err)
        return False, size_err

    # 2. JSON schema validation
    try:
        jsonschema.validate(instance=arguments, schema=schema)
    except jsonschema.ValidationError as e:
        # Return a sanitized message (no full schema exposure)
        msg = e.message
        if e.path:
            field_path = ".".join(str(p) for p in e.path)
            msg = f"Invalid value for '{field_path}': {e.message}"
        logger.warning("MCP schema violation: tool=%s %s", tool_name, msg)
        return False, msg

    return True, None


def scan_arguments_for_injection(
    tool_name: str,
    arguments: dict,
) -> tuple[bool, str | None]:
    """Scan string arguments for prompt injection patterns.

    Reuses the existing ``PromptInjectionDetector`` from
    ``prompt_injection_guard.py`` to catch injection payloads hidden
    in tool argument values (e.g. a description field).

    Only string values longer than 10 characters are scanned — short
    strings and non-string types cannot carry meaningful payloads.
    Internal keys (prefixed with ``_``) are skipped.

    Args:
        tool_name: Name of the tool being called (for logging).
        arguments: The tool arguments dict to scan.

    Returns:
        ``(True, None)`` if clean, ``(False, error_message)`` if injection detected.
    """
    from app.services.prompt_injection_guard import check_query_safety

    for key, value in arguments.items():
        if key.startswith("_"):
            continue
        if isinstance(value, str) and len(value) > 10:
            is_safe, _reason, injections = check_query_safety(value)
            if not is_safe:
                logger.warning(
                    "MCP_INJECTION_BLOCKED: tool=%s arg=%s pattern=%s severity=%s",
                    tool_name,
                    key,
                    injections[0].pattern if injections else "unknown",
                    injections[0].severity if injections else "unknown",
                )
                return False, f"Input rejected: security concern detected in argument '{key}'"
    return True, None


def validate_tool_output(
    tool_name: str,
    output: Any,
    max_bytes: int = MAX_OUTPUT_SIZE_BYTES,
) -> tuple[Any, bool]:
    """Truncate oversized output.

    Args:
        tool_name: Name of the tool (for logging).
        output: The tool's return value.
        max_bytes: Maximum serialized output size in bytes.

    Returns:
        ``(output, was_truncated)`` — output may be replaced with a truncated
        version if it exceeds ``max_bytes``.
    """
    try:
        serialized = json.dumps(output)
    except (TypeError, ValueError):
        return output, False

    if len(serialized.encode("utf-8")) <= max_bytes:
        return output, False

    logger.warning(
        "MCP output truncated: tool=%s size=%d max=%d",
        tool_name,
        len(serialized.encode("utf-8")),
        max_bytes,
    )

    return {
        "truncated": True,
        "message": f"Output exceeded {max_bytes} bytes and was truncated",
        "partial_data": serialized[:max_bytes].rstrip(),
    }, True


def _redact_secrets_in_dict(data: dict, path: str = "") -> tuple[dict, list[str]]:
    """Recursively scan a dict for secret-like keys and redact them.

    Returns:
        ``(redacted_dict, list_of_redacted_paths)``
    """
    redacted = {}
    findings: list[str] = []

    for k, v in data.items():
        key_lower = k.lower()
        field_path = f"{path}.{k}" if path else k

        # Check if the key itself is a known secret key
        if key_lower in _SECRET_OUTPUT_KEYS:
            redacted[k] = "***REDACTED_BY_SECRET_ZERO_FILTER***"
            findings.append(field_path)
            continue

        # Recurse into nested dicts
        if isinstance(v, dict):
            clean_v, sub_findings = _redact_secrets_in_dict(v, field_path)
            redacted[k] = clean_v
            findings.extend(sub_findings)
        elif isinstance(v, list):
            clean_list = []
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    clean_item, sub_findings = _redact_secrets_in_dict(item, f"{field_path}[{i}]")
                    clean_list.append(clean_item)
                    findings.extend(sub_findings)
                else:
                    clean_list.append(item)
            redacted[k] = clean_list
        elif isinstance(v, str):
            # Check if the string value matches secret patterns
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.match(v):
                    redacted[k] = "***REDACTED_BY_SECRET_ZERO_FILTER***"
                    findings.append(f"{field_path}(value_pattern)")
                    break
            else:
                redacted[k] = v
        else:
            redacted[k] = v

    return redacted, findings


def scan_output_for_secrets(tool_name: str, output: Any) -> Any:
    """Scan tool output for credential-like fields and redact them.

    This is the secret-zero check: secrets must never reach the model path.

    Args:
        tool_name: Name of the tool (for logging).
        output: The tool's return value.

    Returns:
        Output with secret fields redacted.
    """
    if not isinstance(output, dict):
        return output

    redacted, findings = _redact_secrets_in_dict(output)

    if findings:
        logger.warning(
            "SECRET_ZERO: tool=%s leaked %d secret field(s): %s",
            tool_name,
            len(findings),
            ", ".join(findings),
        )

    return redacted
