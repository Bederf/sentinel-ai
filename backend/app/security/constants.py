"""
Security Constants.

All security thresholds, limits, and configuration values
for the SENTINEL security module. No magic numbers in
security-relevant code -- everything imports from here.
"""

# ---------------------------------------------------------------------------
# Prompt Guard Scoring Thresholds (0.0 = safe, 1.0 = clearly malicious)
# ---------------------------------------------------------------------------
DIRECT_BLOCK_THRESHOLD: float = 0.7
INDIRECT_BLOCK_THRESHOLD: float = 0.5
WEBHOOK_BLOCK_THRESHOLD: float = 0.5
REWRITE_THRESHOLD: float = 0.3

# ---------------------------------------------------------------------------
# Input Limits
# ---------------------------------------------------------------------------
MAX_CHAT_MESSAGE_LENGTH: int = 4_000  # characters

# ---------------------------------------------------------------------------
# Upload Limits
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# Trust Levels
# ---------------------------------------------------------------------------
TRUST_LEVELS: dict[str, int] = {
    "VERIFIED": 3,
    "STANDARD": 2,
    "UNTRUSTED": 1,
    "QUARANTINED": 0,
}

# ---------------------------------------------------------------------------
# Role Levels (higher = more privileged)
# ---------------------------------------------------------------------------
ROLE_LEVELS: dict[str, int] = {
    "bot_agent": 1,
    "auditor": 1,
    "operator": 2,
    "developer": 3,
    "admin": 4,
}
