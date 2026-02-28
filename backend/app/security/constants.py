"""
Security Constants.

All security thresholds, limits, and configuration values
for the SENTINEL security module. No magic numbers in
security-relevant code -- everything imports from here.
"""

import os
import re

# ---------------------------------------------------------------------------
# Prompt Guard Scoring Thresholds (0.0 = safe, 1.0 = clearly malicious)
#
# DIRECT  = user typing in chat box (highest tolerance)
# INDIRECT = tool argument strings, injected context
# WEBHOOK = external system payloads (email intake, WhatsApp)
# REWRITE = borderline score: sanitize instead of blocking
# ---------------------------------------------------------------------------
DIRECT_BLOCK_THRESHOLD: float = 0.7
INDIRECT_BLOCK_THRESHOLD: float = 0.5
WEBHOOK_BLOCK_THRESHOLD: float = 0.5
REWRITE_THRESHOLD: float = 0.3

# ---------------------------------------------------------------------------
# Input Limits
# ---------------------------------------------------------------------------
MAX_CHAT_MESSAGE_LENGTH: int = 4_000  # characters
MAX_WEBHOOK_BODY_SIZE: int = 1 * 1024 * 1024  # 1 MB
SITE_ID_PATTERN: re.Pattern = re.compile(r"^site-\d{3}$")  # e.g. site-002

# ---------------------------------------------------------------------------
# Upload Limits (document scanner)
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB
MAX_PDF_PAGES: int = 200
MAX_PDF_TEXT_SIZE: int = 500 * 1024  # 500 KB extracted text
PDF_PARSE_TIMEOUT_SECONDS: int = 30
MAX_IMAGE_PIXELS: int = 100_000_000  # 100 megapixels
MAX_IMAGE_DECODED_SIZE: int = 100 * 1024 * 1024  # 100 MB decoded

# ---------------------------------------------------------------------------
# Allowed Magic Bytes (file type verification)
#
# First N bytes of a file must match one of these prefixes.
# ---------------------------------------------------------------------------
ALLOWED_MAGIC_BYTES: dict[str, bytes] = {
    "JPEG": b"\xff\xd8\xff",
    "PNG": b"\x89PNG\r\n\x1a\n",
    "PDF": b"%PDF",
}

# ---------------------------------------------------------------------------
# Output Filtering (SSE buffer, tool result caps)
# ---------------------------------------------------------------------------
SSE_BUFFER_FLUSH_SIZE: int = 2_048  # bytes: flush buffer when this full
SSE_SLIDING_WINDOW_SIZE: int = 4_096  # bytes: cross-chunk pattern detection
MAX_TOOL_RESULT_CONTEXT_SIZE: int = 8_000  # chars: max tool output sent to Claude
MAX_TOOL_RESULT_SUMMARY_SIZE: int = 2_000  # chars: truncated summary fallback

# ---------------------------------------------------------------------------
# Step-Up Authentication
#
# Short-lived re-auth tokens for sensitive operations
# (device control, config changes, user management).
# ---------------------------------------------------------------------------
STEP_UP_VALIDITY_SECONDS: int = 900  # 15 minutes

# ---------------------------------------------------------------------------
# Magic Link Authentication
# ---------------------------------------------------------------------------
MAGIC_LINK_TTL_SECONDS: int = 900  # 15 minutes
MAGIC_LINK_MAX_PER_EMAIL_PER_HOUR: int = 3
MAGIC_LINK_MAX_PER_IP_PER_HOUR: int = 10

# ---------------------------------------------------------------------------
# Webhook Rate Limits
# ---------------------------------------------------------------------------
WEBHOOK_RATE_LIMIT_PER_SENDER_PER_MINUTE: int = 30
WEBHOOK_EMAIL_RATE_LIMIT_PER_HOUR: int = 10

# ---------------------------------------------------------------------------
# Audit Logging
# ---------------------------------------------------------------------------
LOG_MAX_ENTRIES: int = 10_000  # max entries in audit_log.json before rotation
REDACTED_SNIPPET_MAX_LENGTH: int = 200  # max chars shown in redacted log snippets

# ---------------------------------------------------------------------------
# Trust Levels
#
# Determines which security checks apply and how strictly.
# Higher value = more trusted = fewer restrictions.
# ---------------------------------------------------------------------------
TRUST_LEVELS: dict[str, int] = {
    "VERIFIED": 3,  # Authenticated user with step-up auth
    "STANDARD": 2,  # Authenticated user (JWT/API key)
    "UNTRUSTED": 1,  # Unauthenticated or demo-mode user
    "QUARANTINED": 0,  # Input that failed a security check
}

# ---------------------------------------------------------------------------
# Antivirus Scanning
#
# When true, uploaded files must pass AV scan before RAG indexing.
# Reads from REQUIRE_AV_SCAN env var; defaults to true in production.
# ---------------------------------------------------------------------------
REQUIRE_AV_SCAN: bool = os.getenv("REQUIRE_AV_SCAN", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Role Levels (higher = more privileged)
#
# Used for authorization checks and tool access gating.
# ---------------------------------------------------------------------------
ROLE_LEVELS: dict[str, int] = {
    "bot_agent": 1,
    "auditor": 1,
    "operator": 2,
    "developer": 3,
    "admin": 4,
}

# ---------------------------------------------------------------------------
# Citation Pattern
#
# Regex to match citation references in AI output.
# Format: [Source: document_title] or [Source: DOC-CODE-123]
# ---------------------------------------------------------------------------
CITATION_PATTERN: re.Pattern = re.compile(r"\[Source:\s*(?P<ref>[^\]]{1,200})\]")
