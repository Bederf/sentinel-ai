"""
Authentication and authorization models for SENTINEL BMS Platform.

Defines auth levels, roles, API key structures, and auth context
used throughout the middleware and endpoint authorization system.

Ported from AimTheLaw auth stack, adapted for BMS domain.
FSR Domain: 4.7 - Logical Access Control
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AuthLevel(str, Enum):
    """Authentication level required for endpoint access.

    Levels are hierarchical: ADMIN > OPERATOR > AUTHENTICATED > PUBLIC
    """
    PUBLIC = "public"              # No auth required (health, docs)
    AUTHENTICATED = "authenticated"  # Valid token required (read endpoints)
    OPERATOR = "operator"          # Operator or above (control endpoints)
    ADMIN = "admin"                # Admin only (configuration, simulation)


class SentinelRole(str, Enum):
    """SENTINEL platform roles mapped to FSR access control requirements.

    Roles determine what a user can do within the application.
    """
    ADMIN = "admin"        # Full platform administration
    OPERATOR = "operator"  # BMS operations, device control, optimization
    DEVELOPER = "developer"  # Development access, debugging, testing
    AUDITOR = "auditor"    # Read-only access for compliance review


# Role hierarchy: higher roles inherit lower role permissions
ROLE_HIERARCHY: Dict[SentinelRole, int] = {
    SentinelRole.ADMIN: 4,
    SentinelRole.DEVELOPER: 3,
    SentinelRole.OPERATOR: 2,
    SentinelRole.AUDITOR: 1,
}

# Map AuthLevel to minimum required role
AUTH_LEVEL_TO_MIN_ROLE: Dict[AuthLevel, Optional[SentinelRole]] = {
    AuthLevel.PUBLIC: None,
    AuthLevel.AUTHENTICATED: SentinelRole.AUDITOR,
    AuthLevel.OPERATOR: SentinelRole.OPERATOR,
    AuthLevel.ADMIN: SentinelRole.ADMIN,
}


@dataclass
class AuthContext:
    """Context object holding authenticated user information.

    Attached to request.state.auth after successful authentication.
    Available throughout the request lifecycle.
    """
    user_id: str
    role: SentinelRole
    auth_method: str  # "bearer_token", "api_key", "demo_mode"
    source_ip: str
    email: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    api_key_id: Optional[str] = None
    authenticated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_role(self, required_role: SentinelRole) -> bool:
        """Check if user has the required role or higher."""
        user_level = ROLE_HIERARCHY.get(self.role, 0)
        required_level = ROLE_HIERARCHY.get(required_role, 999)
        return user_level >= required_level

    def has_auth_level(self, level: AuthLevel) -> bool:
        """Check if user meets the required auth level."""
        min_role = AUTH_LEVEL_TO_MIN_ROLE.get(level)
        if min_role is None:
            return True  # PUBLIC level, always passes
        return self.has_role(min_role)

    def has_scope(self, scope: str) -> bool:
        """Check if user has a specific API scope."""
        if "admin:all" in self.scopes:
            return True
        return scope in self.scopes

    def to_dict(self) -> Dict[str, Any]:
        """Serialize auth context for logging/audit."""
        return {
            "user_id": self.user_id,
            "role": self.role.value,
            "auth_method": self.auth_method,
            "source_ip": self.source_ip,
            "email": self.email,
            "scopes": self.scopes,
            "api_key_id": self.api_key_id,
            "authenticated_at": self.authenticated_at.isoformat(),
        }


@dataclass
class APIKeyInfo:
    """API key information for service account authentication.

    API keys use the prefix 'sent_sk_' to identify SENTINEL service keys.
    """
    key_id: str
    key_hash: str
    owner: str  # Human owner of the service account
    description: str
    role: SentinelRole
    scopes: List[str]
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    is_active: bool = True
    rate_limit_per_minute: int = 60

    @property
    def is_expired(self) -> bool:
        """Check if the API key has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


def generate_api_key() -> tuple[str, str]:
    """Generate a new SENTINEL API key and its hash.

    Returns:
        Tuple of (plaintext_key, key_hash)
        The plaintext key should be shown to the user once and never stored.
    """
    # Generate 32-byte random key
    random_part = secrets.token_hex(32)
    plaintext_key = f"sent_sk_{random_part}"
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    return plaintext_key, key_hash


def verify_api_key(plaintext_key: str, stored_hash: str) -> bool:
    """Verify an API key against its stored hash.

    Args:
        plaintext_key: The API key provided by the client
        stored_hash: The SHA-256 hash stored in the database

    Returns:
        True if the key is valid
    """
    computed_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    return secrets.compare_digest(computed_hash, stored_hash)


# =============================================================================
# Endpoint Classification
# =============================================================================

# Endpoints that require no authentication
PUBLIC_ENDPOINTS = {
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/openapi.json",
}

# Endpoint path prefixes mapped to their required auth level
# More specific paths should be listed first (longest prefix match wins)
ENDPOINT_AUTH_LEVELS: List[tuple[str, AuthLevel]] = [
    # Admin-only endpoints
    ("/api/simulation/", AuthLevel.ADMIN),

    # Operator endpoints (control actions)
    ("/api/devices/", AuthLevel.OPERATOR),       # Device control
    ("/api/optimization/", AuthLevel.OPERATOR),    # Optimization actions
    ("/api/mcp/simbiot/call", AuthLevel.OPERATOR),  # MCP tool execution
    ("/api/hvac/", AuthLevel.OPERATOR),            # HVAC control

    # Authenticated endpoints (read access)
    ("/api/chat", AuthLevel.AUTHENTICATED),
    ("/api/hybrid-chat", AuthLevel.AUTHENTICATED),
    ("/api/equipment", AuthLevel.AUTHENTICATED),
    ("/api/sensors", AuthLevel.AUTHENTICATED),
    ("/api/alerts", AuthLevel.AUTHENTICATED),
    ("/api/sites", AuthLevel.AUTHENTICATED),
    ("/api/stats", AuthLevel.AUTHENTICATED),
    ("/api/energy", AuthLevel.AUTHENTICATED),
    ("/api/predictions", AuthLevel.AUTHENTICATED),
    ("/api/ml/", AuthLevel.AUTHENTICATED),
    ("/api/survival/", AuthLevel.AUTHENTICATED),
    ("/api/rag/", AuthLevel.AUTHENTICATED),
    ("/api/integration/", AuthLevel.AUTHENTICATED),
    ("/api/features/", AuthLevel.AUTHENTICATED),
    ("/api/data-quality/", AuthLevel.AUTHENTICATED),
    ("/api/inspection/", AuthLevel.AUTHENTICATED),
    ("/api/complaints/", AuthLevel.AUTHENTICATED),
    ("/api/audit/", AuthLevel.AUTHENTICATED),
    ("/api/mcp/simbiot/tools", AuthLevel.AUTHENTICATED),
    ("/api/mcp/simbiot/info", AuthLevel.AUTHENTICATED),
    ("/api/niagara/", AuthLevel.AUTHENTICATED),
    ("/api/buildings/", AuthLevel.AUTHENTICATED),
]


def get_required_auth_level(path: str) -> AuthLevel:
    """Determine the required auth level for a given endpoint path.

    Uses longest prefix match to find the most specific rule.

    Args:
        path: The request URL path

    Returns:
        The required AuthLevel for the endpoint
    """
    # Check public endpoints first (exact match)
    if path in PUBLIC_ENDPOINTS:
        return AuthLevel.PUBLIC

    # Check path prefixes (longest match wins)
    for prefix, level in ENDPOINT_AUTH_LEVELS:
        if path.startswith(prefix):
            return level

    # Default: require authentication for any unclassified endpoint
    return AuthLevel.AUTHENTICATED
