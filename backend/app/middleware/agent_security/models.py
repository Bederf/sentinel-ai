"""Agent Security Models — Phase 120: Agent Security Middleware.

Defines the permission matrix, session model, confirmation token, and audit
entry for the agent security gate. The permission matrix is a frozen registry
(following QualityGatePolicy pattern) mapping SentinelRole x AgentToolName
to a PolicyDecision.

Design rules:
- EQUIPMENT_CONTROL always requires confirmation, even for ADMIN
- SHELL always requires confirmation for ADMIN, DENY for all others
- Default-deny: any role/tool pair not in the matrix is DENY
- Import SentinelRole from app.models.auth — never duplicate the enum
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.auth import SentinelRole


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentToolName(str, Enum):
    """Tool categories that the agent security gate controls."""

    BMS_READ = "BMS_READ"
    WORK_ORDERS = "WORK_ORDERS"
    EQUIPMENT_CONTROL = "EQUIPMENT_CONTROL"
    TELEGRAM_BOT = "TELEGRAM_BOT"
    EMAIL_SMTP = "EMAIL_SMTP"
    SHELL = "SHELL"
    DATABASE_WRITE = "DATABASE_WRITE"
    MCP_EXPOSE = "MCP_EXPOSE"


class PolicyDecision(str, Enum):
    """Result of a permission matrix lookup."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    READ_ONLY = "READ_ONLY"


# ---------------------------------------------------------------------------
# Permission Matrix — frozen registry (role x tool -> decision)
# ---------------------------------------------------------------------------

# Keys are SentinelRole enum values for the 4 existing roles.
# "bot_agent" is a string placeholder until Plan 120-03 adds BOT_AGENT to
# the SentinelRole enum.

PERMISSION_MATRIX: dict = {
    # ----- ADMIN -----
    SentinelRole.ADMIN: {
        AgentToolName.BMS_READ: PolicyDecision.ALLOW,
        AgentToolName.WORK_ORDERS: PolicyDecision.ALLOW,
        AgentToolName.EQUIPMENT_CONTROL: PolicyDecision.REQUIRE_CONFIRMATION,
        AgentToolName.TELEGRAM_BOT: PolicyDecision.ALLOW,
        AgentToolName.EMAIL_SMTP: PolicyDecision.ALLOW,
        AgentToolName.SHELL: PolicyDecision.REQUIRE_CONFIRMATION,
        AgentToolName.DATABASE_WRITE: PolicyDecision.ALLOW,
        AgentToolName.MCP_EXPOSE: PolicyDecision.ALLOW,
    },
    # ----- OPERATOR -----
    SentinelRole.OPERATOR: {
        AgentToolName.BMS_READ: PolicyDecision.ALLOW,
        AgentToolName.WORK_ORDERS: PolicyDecision.ALLOW,
        AgentToolName.EQUIPMENT_CONTROL: PolicyDecision.REQUIRE_CONFIRMATION,
        AgentToolName.TELEGRAM_BOT: PolicyDecision.ALLOW,
        AgentToolName.EMAIL_SMTP: PolicyDecision.REQUIRE_CONFIRMATION,
        AgentToolName.SHELL: PolicyDecision.DENY,
        AgentToolName.DATABASE_WRITE: PolicyDecision.ALLOW,
        AgentToolName.MCP_EXPOSE: PolicyDecision.READ_ONLY,
    },
    # ----- DEVELOPER -----
    SentinelRole.DEVELOPER: {
        AgentToolName.BMS_READ: PolicyDecision.ALLOW,
        AgentToolName.WORK_ORDERS: PolicyDecision.READ_ONLY,
        AgentToolName.EQUIPMENT_CONTROL: PolicyDecision.REQUIRE_CONFIRMATION,
        AgentToolName.TELEGRAM_BOT: PolicyDecision.READ_ONLY,
        AgentToolName.EMAIL_SMTP: PolicyDecision.DENY,
        AgentToolName.SHELL: PolicyDecision.DENY,
        AgentToolName.DATABASE_WRITE: PolicyDecision.REQUIRE_CONFIRMATION,
        AgentToolName.MCP_EXPOSE: PolicyDecision.ALLOW,
    },
    # ----- AUDITOR -----
    SentinelRole.AUDITOR: {
        AgentToolName.BMS_READ: PolicyDecision.READ_ONLY,
        AgentToolName.WORK_ORDERS: PolicyDecision.READ_ONLY,
        AgentToolName.EQUIPMENT_CONTROL: PolicyDecision.DENY,
        AgentToolName.TELEGRAM_BOT: PolicyDecision.DENY,
        AgentToolName.EMAIL_SMTP: PolicyDecision.DENY,
        AgentToolName.SHELL: PolicyDecision.DENY,
        AgentToolName.DATABASE_WRITE: PolicyDecision.DENY,
        AgentToolName.MCP_EXPOSE: PolicyDecision.READ_ONLY,
    },
    # ----- BOT_AGENT (Phase 120-03: promoted from string placeholder to enum key) -----
    SentinelRole.BOT_AGENT: {
        AgentToolName.BMS_READ: PolicyDecision.READ_ONLY,
        AgentToolName.WORK_ORDERS: PolicyDecision.ALLOW,
        AgentToolName.EQUIPMENT_CONTROL: PolicyDecision.DENY,
        AgentToolName.TELEGRAM_BOT: PolicyDecision.ALLOW,
        AgentToolName.EMAIL_SMTP: PolicyDecision.REQUIRE_CONFIRMATION,
        AgentToolName.SHELL: PolicyDecision.DENY,
        AgentToolName.DATABASE_WRITE: PolicyDecision.ALLOW,
        AgentToolName.MCP_EXPOSE: PolicyDecision.READ_ONLY,
    },
}


# ---------------------------------------------------------------------------
# AgentSession
# ---------------------------------------------------------------------------


class AgentSession(BaseModel):
    """Tracks an authenticated agent session with building-scoped access."""

    session_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    owner_id: str
    role: str  # SentinelRole value (including "bot_agent")
    tenant_id: str
    building_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=1))

    @property
    def is_expired(self) -> bool:
        """Check whether this session has passed its expiry time."""
        return datetime.utcnow() > self.expires_at

    def has_building_access(self, building_id: str) -> bool:
        """Check if the session grants access to a specific building.

        Admins have implicit access to all buildings within their tenant.
        All other roles are restricted to the explicit building_ids list.
        """
        if self.role == SentinelRole.ADMIN.value or self.role == SentinelRole.ADMIN:
            return True
        return building_id in self.building_ids


# ---------------------------------------------------------------------------
# ConfirmationToken
# ---------------------------------------------------------------------------


def _generate_token() -> str:
    """Generate a 4-character uppercase hex token for confirmation prompts."""
    return secrets.token_hex(2).upper()


class ConfirmationToken(BaseModel):
    """Short-lived token for 2-step confirmation of dangerous actions.

    The plaintext token is shown to the user; the hash is stored server-side.
    Verification uses secrets.compare_digest for timing-safe comparison.
    """

    token: str = Field(default_factory=_generate_token)
    token_hash: str = ""
    session_id: str
    tool: str  # AgentToolName value
    target: str
    action_summary: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(seconds=60))

    def model_post_init(self, __context: object) -> None:
        """Compute SHA-256 hash of the token after initialization."""
        if not self.token_hash:
            self.token_hash = hashlib.sha256(self.token.encode()).hexdigest()

    @property
    def is_expired(self) -> bool:
        """Check whether the confirmation window has elapsed."""
        return datetime.utcnow() > self.expires_at

    def verify(self, user_token: str) -> bool:
        """Verify a user-supplied token using timing-safe comparison.

        Args:
            user_token: The token string entered by the user.

        Returns:
            True if the token matches and has not expired.
        """
        if self.is_expired:
            return False
        user_hash = hashlib.sha256(user_token.encode()).hexdigest()
        return secrets.compare_digest(user_hash, self.token_hash)


# ---------------------------------------------------------------------------
# AgentAuditEntry
# ---------------------------------------------------------------------------


class AgentAuditEntry(BaseModel):
    """Immutable audit record for every agent security evaluation."""

    entry_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    owner_id: str
    role: str
    tenant_id: str = ""
    tool: str  # AgentToolName value
    action: str  # HTTP method or action descriptor
    target: str  # Resource path or identifier
    policy_decision: str  # PolicyDecision value
    confirmation_required: bool = False
    confirmation_token_hash: Optional[str] = None
    confirmation_result: Optional[str] = None  # "verified" | "expired" | "mismatch"
    error: Optional[str] = None
    ip_address: Optional[str] = None
    channel: Optional[str] = None  # "api" | "telegram" | "mcp"
