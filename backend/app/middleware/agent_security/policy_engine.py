"""Tool Policy Engine — Phase 120: Agent Security Middleware.

Stateless evaluator (following QualityGateEvaluator pattern) that checks every
agent tool invocation against the frozen PERMISSION_MATRIX. The engine:

1. Validates session (expiry, building scope)
2. Looks up the permission matrix (role x tool -> decision)
3. Downgrades READ_ONLY + write action to DENY
4. Issues ConfirmationTokens for REQUIRE_CONFIRMATION decisions
5. Logs every evaluation as an AgentAuditEntry

Storage is in-memory for the current single-worker deployment.

# TODO(production): Replace with Redis-backed store when scaling to
# multiple workers. Key structure:
#   sentinel:confirmations:{session_id} → token_hash (TTL 60s)
#   sentinel:breaker:{agent_id} → state JSON (TTL 5min)
#   sentinel:ratelimit:{identity}:{window} → counter (TTL = window)
"""

import logging
from dataclasses import dataclass, field

from app.middleware.agent_security.models import (
    PERMISSION_MATRIX,
    AgentAuditEntry,
    AgentSession,
    AgentToolName,
    ConfirmationToken,
    PolicyDecision,
)
from app.models.auth import SentinelRole

logger = logging.getLogger(__name__)

# HTTP methods considered write operations
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


# ---------------------------------------------------------------------------
# PolicyResult
# ---------------------------------------------------------------------------


@dataclass
class PolicyResult:
    """Outcome of a single policy evaluation."""

    decision: PolicyDecision
    reason: str
    confirmation_token: ConfirmationToken | None = None
    audit_entry: AgentAuditEntry | None = field(default=None, repr=False)

    @property
    def is_allowed(self) -> bool:
        """True when the action may proceed without further steps."""
        return self.decision == PolicyDecision.ALLOW

    @property
    def needs_confirmation(self) -> bool:
        """True when the user must supply a confirmation token."""
        return self.decision == PolicyDecision.REQUIRE_CONFIRMATION


# ---------------------------------------------------------------------------
# ToolPolicyEngine
# ---------------------------------------------------------------------------


class ToolPolicyEngine:
    """Evaluates agent tool invocations against the permission matrix.

    Follows the QualityGateEvaluator pattern: a stateless evaluator backed by
    a frozen policy registry (PERMISSION_MATRIX). In-memory pending confirmation
    store and audit log for the single-worker deployment.

    Usage:
        engine = ToolPolicyEngine()
        result = engine.evaluate(session, AgentToolName.BMS_READ, "GET", "/api/eq")
        if result.needs_confirmation:
            # show token to user, then...
            confirmed = engine.confirm_action(session.session_id, user_input)
    """

    def __init__(self) -> None:
        # TODO(production): Replace with Redis-backed store when scaling to
        # multiple workers. Key structure:
        #   sentinel:confirmations:{session_id} → token_hash (TTL 60s)
        #   sentinel:breaker:{agent_id} → state JSON (TTL 5min)
        #   sentinel:ratelimit:{identity}:{window} → counter (TTL = window)
        self._pending_confirmations: dict[str, ConfirmationToken] = {}
        self._audit_log: list[AgentAuditEntry] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        session: AgentSession,
        tool: AgentToolName,
        action: str,
        target: str,
        site_id: str | None = None,
    ) -> PolicyResult:
        """Evaluate a tool invocation against session scope and permission matrix.

        Checks are applied in order (first failure wins):
        1. Session expiry
        2. Building scope (if site_id provided)
        3. Permission matrix lookup (role x tool)
        4. Write-action downgrade (READ_ONLY + write method -> DENY)

        Args:
            session: The authenticated agent session.
            tool: Tool category being invoked.
            action: HTTP method or action descriptor (e.g. "GET", "POST").
            target: Resource path or identifier.
            site_id: Optional building scope check.

        Returns:
            PolicyResult with decision, reason, and optional confirmation token.
        """
        # Check 1: Session expiry
        if session.is_expired:
            result = self._make_result(
                PolicyDecision.DENY,
                "Session expired",
                session,
                tool,
                action,
                target,
            )
            logger.warning(
                "agent_security.deny session_expired session_id=%s owner=%s",
                session.session_id,
                session.owner_id,
            )
            return result

        # Check 2: Building scope
        if site_id and not session.has_site_access(site_id):
            result = self._make_result(
                PolicyDecision.DENY,
                f"Building {site_id} not in session scope",
                session,
                tool,
                action,
                target,
            )
            logger.warning(
                "agent_security.deny building_scope session_id=%s building=%s",
                session.session_id,
                site_id,
            )
            return result

        # Check 3: Permission matrix lookup
        decision = self._lookup_decision(session.role, tool)

        # Check 4: Write-action downgrade
        if decision == PolicyDecision.READ_ONLY:
            if action.upper() in _WRITE_METHODS:
                result = self._make_result(
                    PolicyDecision.DENY,
                    f"READ_ONLY permission does not allow {action.upper()} on {tool.value}",
                    session,
                    tool,
                    action,
                    target,
                )
                logger.warning(
                    "agent_security.deny read_only_write session_id=%s tool=%s action=%s",
                    session.session_id,
                    tool.value,
                    action.upper(),
                )
                return result
            # READ_ONLY + GET -> treat as ALLOW
            decision = PolicyDecision.ALLOW

        # Handle REQUIRE_CONFIRMATION — issue a token
        if decision == PolicyDecision.REQUIRE_CONFIRMATION:
            token = ConfirmationToken(
                session_id=session.session_id,
                tool=tool.value,
                target=target,
                action_summary=f"{action.upper()} {target} via {tool.value}",
            )
            self._pending_confirmations[session.session_id] = token
            result = self._make_result(
                PolicyDecision.REQUIRE_CONFIRMATION,
                f"Confirmation required for {tool.value}. Token: {token.token}",
                session,
                tool,
                action,
                target,
                confirmation_token=token,
            )
            logger.info(
                "agent_security.confirm_required session_id=%s tool=%s target=%s",
                session.session_id,
                tool.value,
                target,
            )
            return result

        # ALLOW or DENY
        if decision == PolicyDecision.ALLOW:
            result = self._make_result(
                PolicyDecision.ALLOW,
                f"Allowed: {tool.value} for role {session.role}",
                session,
                tool,
                action,
                target,
            )
            logger.info(
                "agent_security.allow session_id=%s tool=%s role=%s",
                session.session_id,
                tool.value,
                session.role,
            )
            return result

        # Default: DENY (covers PolicyDecision.DENY and any unknown state)
        result = self._make_result(
            PolicyDecision.DENY,
            f"Denied: {tool.value} for role {session.role}",
            session,
            tool,
            action,
            target,
        )
        logger.warning(
            "agent_security.deny policy_matrix session_id=%s tool=%s role=%s",
            session.session_id,
            tool.value,
            session.role,
        )
        return result

    def confirm_action(
        self,
        session_id: str,
        user_token: str,
    ) -> PolicyResult:
        """Validate a user-supplied confirmation token.

        Looks up the pending confirmation for the session, checks expiry,
        and performs timing-safe comparison.

        Args:
            session_id: The session that initiated the confirmation.
            user_token: The token string entered by the user.

        Returns:
            PolicyResult with ALLOW on success, DENY on failure.
        """
        pending = self._pending_confirmations.get(session_id)

        if pending is None:
            logger.warning(
                "agent_security.confirm_fail no_pending session_id=%s",
                session_id,
            )
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason="No pending confirmation for this session",
            )

        if pending.is_expired:
            # Clean up expired token
            self._pending_confirmations.pop(session_id, None)
            self._record_confirmation_result(pending, "expired")
            logger.warning(
                "agent_security.confirm_fail expired session_id=%s tool=%s",
                session_id,
                pending.tool,
            )
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason="Confirmation token expired (60s window)",
            )

        if pending.verify(user_token):
            # Success — remove from pending
            self._pending_confirmations.pop(session_id, None)
            self._record_confirmation_result(pending, "verified")
            logger.info(
                "agent_security.confirm_ok session_id=%s tool=%s target=%s",
                session_id,
                pending.tool,
                pending.target,
            )
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                reason=f"Confirmed: {pending.tool} on {pending.target}",
            )

        # Token mismatch
        self._record_confirmation_result(pending, "mismatch")
        logger.warning(
            "agent_security.confirm_fail mismatch session_id=%s tool=%s",
            session_id,
            pending.tool,
        )
        return PolicyResult(
            decision=PolicyDecision.DENY,
            reason="Confirmation token mismatch",
        )

    def get_audit_log(self) -> list[AgentAuditEntry]:
        """Return a copy of the in-memory audit log.

        TODO(production): Replace with Redis/Supabase query.
        """
        return list(self._audit_log)

    def get_pending_confirmations_count(self) -> int:
        """Return the number of pending (unexpired) confirmations."""
        return len(self._pending_confirmations)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup_decision(self, role: str, tool: AgentToolName) -> PolicyDecision:
        """Look up the permission matrix for a role/tool pair.

        Handles both SentinelRole enum values and string keys (e.g. "bot_agent").
        Default-deny: any unmapped pair returns DENY.
        """
        # Try matching against SentinelRole enum members first
        for sentinel_role in SentinelRole:
            if role == sentinel_role.value or role == sentinel_role:
                role_perms = PERMISSION_MATRIX.get(sentinel_role)
                if role_perms:
                    return role_perms.get(tool, PolicyDecision.DENY)

        # Try string key (e.g. "bot_agent" placeholder)
        role_perms = PERMISSION_MATRIX.get(role)
        if role_perms:
            return role_perms.get(tool, PolicyDecision.DENY)

        # Default-deny for unknown roles
        return PolicyDecision.DENY

    def _make_result(
        self,
        decision: PolicyDecision,
        reason: str,
        session: AgentSession,
        tool: AgentToolName,
        action: str,
        target: str,
        confirmation_token: ConfirmationToken | None = None,
    ) -> PolicyResult:
        """Create a PolicyResult and append an audit entry."""
        audit_entry = AgentAuditEntry(
            session_id=session.session_id,
            owner_id=session.owner_id,
            role=session.role,
            tenant_id=session.tenant_id,
            tool=tool.value,
            action=action,
            target=target,
            policy_decision=decision.value,
            confirmation_required=(decision == PolicyDecision.REQUIRE_CONFIRMATION),
            confirmation_token_hash=(confirmation_token.token_hash if confirmation_token else None),
        )
        self._audit_log.append(audit_entry)

        return PolicyResult(
            decision=decision,
            reason=reason,
            confirmation_token=confirmation_token,
            audit_entry=audit_entry,
        )

    def _record_confirmation_result(
        self,
        token: ConfirmationToken,
        result: str,
    ) -> None:
        """Update the most recent audit entry for a confirmation outcome."""
        # Walk backwards to find the matching entry
        for entry in reversed(self._audit_log):
            if entry.session_id == token.session_id and entry.confirmation_token_hash == token.token_hash:
                entry.confirmation_result = result
                break


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

policy_engine = ToolPolicyEngine()
