"""Agent Security Middleware — Phase 120.

Default-deny permission matrix with 2-step confirmation for dangerous actions.
Evaluates every agent tool invocation against role-based policy.

Usage:
    from app.middleware.agent_security import policy_engine, AgentSession

    session = AgentSession(owner_id="u1", role="admin", tenant_id="t1", site_ids=["b1"])
    result = policy_engine.evaluate(session, AgentToolName.BMS_READ, "GET", "/api/equipment")
    if result.is_allowed:
        ...  # proceed
"""

from app.middleware.agent_security.circuit_breaker import (
    AgentRateLimiter,
    BreakerCheckResult,
    BreakerState,
    CircuitBreaker,
    QuotaTier,
    RateLimitResult,
    circuit_breaker,
    rate_limiter,
)
from app.middleware.agent_security.middleware import (
    AgentSecurityMiddleware,
    check_unmapped_routes,
)
from app.middleware.agent_security.models import (
    PERMISSION_MATRIX,
    AgentAuditEntry,
    AgentSession,
    AgentToolName,
    ConfirmationToken,
    PolicyDecision,
)
from app.middleware.agent_security.policy_engine import (
    PolicyResult,
    ToolPolicyEngine,
    policy_engine,
)
from app.middleware.agent_security.verification import (
    VerificationEvidence,
    VerificationResult,
    VerificationRunner,
    VerificationStatus,
    verification_runner,
)

__all__ = [
    "PERMISSION_MATRIX",
    "AgentAuditEntry",
    "AgentRateLimiter",
    "AgentSecurityMiddleware",
    "AgentSession",
    "AgentToolName",
    "BreakerCheckResult",
    "BreakerState",
    "CircuitBreaker",
    "ConfirmationToken",
    "PolicyDecision",
    "PolicyResult",
    "QuotaTier",
    "RateLimitResult",
    "ToolPolicyEngine",
    "VerificationEvidence",
    "VerificationResult",
    "VerificationRunner",
    "VerificationStatus",
    "check_unmapped_routes",
    "circuit_breaker",
    "policy_engine",
    "rate_limiter",
    "verification_runner",
]
