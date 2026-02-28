"""
Five-Stage Output Filter Pipeline.

Scans AI-generated output before it reaches the client:
    Stage 1: Secret/credential scanner (extends scan_output_for_secrets + BMS patterns)
    Stage 2: System prompt leak detector (kills response entirely)
    Stage 3: PII redaction (imports existing pii_guard.py; skips for ADMIN)
    Stage 4: Internal path/hostname scrubber
    Stage 5: Error/traceback sanitizer

Applied both to batch responses and streaming (via sse_buffer.py).
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage 1: Secret / Credential Patterns
# ---------------------------------------------------------------------------

# BMS-specific patterns (IP, protocol URLs, DB strings, JWT, Supabase)
_BMS_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    # IPv4 addresses (private and public) — but not version-like strings (1.2.3)
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED-IP]"),
    # BACnet URLs
    (re.compile(r"bacnet://[^\s\"'<>]+"), "[REDACTED-BACNET]"),
    # Modbus URLs
    (re.compile(r"modbus://[^\s\"'<>]+"), "[REDACTED-MODBUS]"),
    # Niagara URLs
    (re.compile(r"niagara://[^\s\"'<>]+"), "[REDACTED-NIAGARA]"),
    # Database connection strings (jdbc, postgresql, mysql, mongodb)
    (
        re.compile(r"(?:jdbc|postgresql|postgres|mysql|mongodb|redis)://[^\s\"'<>]+"),
        "[REDACTED-DB-URL]",
    ),
    # Supabase URLs (project ref pattern)
    (re.compile(r"https?://[a-z0-9]+\.supabase\.co[^\s\"'<>]*"), "[REDACTED-SUPABASE]"),
    # JWT tokens (eyJ... with two dot-separated segments)
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?\b"),
        "[REDACTED-JWT]",
    ),
    # API key patterns (sk-ant, sent_sk, sk_test, sk_live, pk_test, pk_live)
    (
        re.compile(r"\b(?:sk-ant|sent_sk|sk_test|sk_live|pk_test|pk_live)[A-Za-z0-9_-]{16,}\b"),
        "[REDACTED-API-KEY]",
    ),
    # Bearer tokens in free text
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"), "[REDACTED-BEARER]"),
]

# ---------------------------------------------------------------------------
# Stage 2: System Prompt Leak Detection
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT_LEAK_PATTERNS: list[re.Pattern] = [
    re.compile(r"BEGIN\s+SYSTEM\s+PROMPT", re.IGNORECASE),
    re.compile(r"<system_prompt>", re.IGNORECASE),
    re.compile(r"here\s+(?:is|are)\s+(?:my|the)\s+system\s+instructions", re.IGNORECASE),
    re.compile(r"my\s+system\s+prompt\s+(?:is|says|reads)", re.IGNORECASE),
    re.compile(r"</system_prompt>", re.IGNORECASE),
    re.compile(r"END\s+SYSTEM\s+PROMPT", re.IGNORECASE),
    re.compile(r"SYSTEM\s+INSTRUCTIONS:", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Stage 4: Internal Paths & Hostnames
# ---------------------------------------------------------------------------
_INTERNAL_PATH_PATTERNS: list[tuple[re.Pattern, str]] = [
    # /opt/bms-intelligence/... paths
    (re.compile(r"/opt/bms-intelligence/[^\s\"'<>]*"), "[internal path]"),
    # /home/user/... paths
    (re.compile(r"/home/[^\s\"'<>]+"), "[internal path]"),
    # Python source references like backend/app/foo.py:123
    (re.compile(r"backend/app/[^\s\"'<>]*\.py(?::\d+)?"), "[internal reference]"),
    # container_id=hex
    (re.compile(r"container_id=[0-9a-f]{12,64}"), "[internal reference]"),
]

# ---------------------------------------------------------------------------
# Stage 5: Error / Traceback Sanitizer
# ---------------------------------------------------------------------------
_TRACEBACK_PATTERN = re.compile(
    r"Traceback \(most recent call last\):.*?(?=\n\n|\n[A-Z]|\Z)",
    re.DOTALL,
)
_ERROR_LINE_PATTERN = re.compile(
    r"^(?:[\w.]*(?:Error|Exception|Warning)): .+$",
    re.MULTILINE,
)
_ENV_VAR_PATTERN = re.compile(
    r"\b[A-Z][A-Z0-9_]{2,}=[^\s]+",
)

_GENERIC_ERROR_MSG = "An internal error occurred."


# ---------------------------------------------------------------------------
# FilterResult
# ---------------------------------------------------------------------------
@dataclass
class FilterResult:
    """Result of running the output filter pipeline."""

    text: str
    kill_response: bool = False
    redactions: list[str] = field(default_factory=list)

    def get_safe_suffix(self) -> str:
        """Return a safe suffix summarizing redactions for audit logging."""
        if not self.redactions:
            return ""
        return f" [{len(self.redactions)} redaction(s): {', '.join(self.redactions[:5])}]"


# ---------------------------------------------------------------------------
# Pipeline Implementation
# ---------------------------------------------------------------------------


def _stage_1_secrets(text: str, redactions: list[str]) -> str:
    """Stage 1: Scan and redact secrets/credentials."""
    for pattern, replacement in _BMS_SECRET_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            text = pattern.sub(replacement, text)
            redactions.append(f"secret:{replacement}")
    return text


def _stage_2_system_prompt_leak(text: str) -> bool:
    """Stage 2: Detect system prompt leaks. Returns True if leak detected."""
    for pattern in _SYSTEM_PROMPT_LEAK_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _stage_3_pii(text: str, redactions: list[str], user_role: str | None) -> str:
    """Stage 3: PII redaction. Skipped for ADMIN role."""
    if user_role and user_role.lower() == "admin":
        return text

    from app.middleware.pii_guard import pii_guard

    result = pii_guard.redact(text)
    if result.redaction_count > 0:
        text = result.redacted_text
        for pii_type in result.pii_found:
            redactions.append(f"pii:{pii_type}")
    return text


def _stage_4_internal_paths(text: str, redactions: list[str]) -> str:
    """Stage 4: Scrub internal paths and hostnames."""
    for pattern, replacement in _INTERNAL_PATH_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            text = pattern.sub(replacement, text)
            redactions.append(f"path:{replacement}")
    return text


def _stage_5_error_sanitizer(text: str, redactions: list[str]) -> str:
    """Stage 5: Sanitize tracebacks, error lines, and env var patterns."""
    # Replace full tracebacks
    if _TRACEBACK_PATTERN.search(text):
        text = _TRACEBACK_PATTERN.sub(_GENERIC_ERROR_MSG, text)
        redactions.append("error:traceback")

    # Replace standalone Error/Exception lines
    if _ERROR_LINE_PATTERN.search(text):
        text = _ERROR_LINE_PATTERN.sub(_GENERIC_ERROR_MSG, text)
        redactions.append("error:exception_line")

    # Remove ENV_VAR=value patterns
    if _ENV_VAR_PATTERN.search(text):
        text = _ENV_VAR_PATTERN.sub("", text)
        redactions.append("error:env_var")

    return text


def run_output_filter_pipeline(
    text: str,
    user_role: str | None = None,
) -> FilterResult:
    """Run the five-stage output filter pipeline.

    Stages (in order):
        1. Secret/credential scanner
        2. System prompt leak detector (kills response)
        3. PII guard (skipped for ADMIN)
        4. Internal path scrubber
        5. Error/traceback sanitizer

    Args:
        text: The text to filter.
        user_role: The role of the current user (e.g. "admin", "operator").

    Returns:
        FilterResult with filtered text, kill flag, and redaction list.
    """
    if not text:
        return FilterResult(text=text)

    redactions: list[str] = []

    # Stage 1: Secrets
    text = _stage_1_secrets(text, redactions)

    # Stage 2: System prompt leak detection — kill the entire response
    if _stage_2_system_prompt_leak(text):
        logger.warning("OUTPUT_FILTER: System prompt leak detected — killing response")
        return FilterResult(
            text="[Response blocked by security filter]",
            kill_response=True,
            redactions=["system_prompt_leak"],
        )

    # Stage 3: PII redaction (skip for admin)
    text = _stage_3_pii(text, redactions, user_role)

    # Stage 4: Internal paths
    text = _stage_4_internal_paths(text, redactions)

    # Stage 5: Error sanitizer
    text = _stage_5_error_sanitizer(text, redactions)

    if redactions:
        logger.info(
            "OUTPUT_FILTER: %d redaction(s) applied: %s",
            len(redactions),
            ", ".join(redactions[:10]),
        )

    return FilterResult(text=text, redactions=redactions)
