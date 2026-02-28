"""
SENTINEL Security Module.

Centralized security layer for the SENTINEL BMS platform.
Provides input validation, output filtering, trust management,
audit logging, and policy enforcement for all AI-facing surfaces.

Module structure:
    - pipeline.py       - Orchestrates the full security pipeline (input -> process -> output)
    - prompt_guard.py   - Prompt injection detection and scoring
    - output_filter.py  - Output scanning (secrets, PII, citations)
    - sse_buffer.py     - Streaming output buffer for real-time filtering
    - document_scanner.py - Upload validation (magic bytes, AV, size limits)
    - trust_levels.py   - Trust level assignment for different input sources
    - tool_policy.py    - Per-tool authorization and argument policy
    - step_up.py        - Step-up authentication for sensitive operations
    - webhook_auth.py   - Webhook sender verification and rate limiting
    - audit_events.py   - Structured security event logging
    - constants.py      - All security thresholds and configuration constants
"""

from app.security.constants import (
    DIRECT_BLOCK_THRESHOLD,
    INDIRECT_BLOCK_THRESHOLD,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_UPLOAD_SIZE,
    ROLE_LEVELS,
    TRUST_LEVELS,
)
from app.security.pipeline import require_role, require_site_access

__all__ = [
    "DIRECT_BLOCK_THRESHOLD",
    "INDIRECT_BLOCK_THRESHOLD",
    "MAX_CHAT_MESSAGE_LENGTH",
    "MAX_UPLOAD_SIZE",
    "ROLE_LEVELS",
    "TRUST_LEVELS",
    "require_role",
    "require_site_access",
]
