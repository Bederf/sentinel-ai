"""
Security Audit Events.

Structured event logging for security-relevant actions:
    - Prompt injection attempts (blocked and borderline)
    - Secret leakage detections
    - Step-up auth challenges
    - Rate limit violations
    - Document scan results
    - Trust level transitions
    - Config and permission changes
    - Webhook anomalies

Events are emitted to the existing AuditLogger (JSON + structured
Loki output) with immediate flush for security events and Telegram
alerts for critical events via Sentry alert_notifier.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from app.security.constants import REDACTED_SNIPPET_MAX_LENGTH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security Event Type Sets
# ---------------------------------------------------------------------------

SECURITY_EVENTS: set[str] = {
    "PROMPT_GUARD_BLOCK",
    "PROMPT_GUARD_REWRITE",
    "OUTPUT_FILTER_BLOCK",
    "SECRET_DETECTED",
    "DOCUMENT_QUARANTINED",
    "RAG_INJECTION_DETECTED",
    "TOOL_DENIED",
    "STEP_UP_FAILED",
    "WEBHOOK_SUSPICIOUS",
    "CONFIG_CHANGE",
    "PERMISSION_CHANGE",
    "RATE_LIMIT_EXCEEDED",
    "BOLA_SITE_DENIED",
    "BOLA_EQUIPMENT_DENIED",
}

# Subset of SECURITY_EVENTS that trigger a Telegram alert to the FM team
ALERT_EVENTS: set[str] = {
    "PROMPT_GUARD_BLOCK",
    "OUTPUT_FILTER_BLOCK",
    "SECRET_DETECTED",
    "DOCUMENT_QUARANTINED",
    "WEBHOOK_SUSPICIOUS",
    "CONFIG_CHANGE",
    "PERMISSION_CHANGE",
}

# Map event types to severity levels for structured logging
_EVENT_SEVERITY: dict[str, str] = {
    "PROMPT_GUARD_BLOCK": "high",
    "PROMPT_GUARD_REWRITE": "medium",
    "OUTPUT_FILTER_BLOCK": "high",
    "SECRET_DETECTED": "critical",
    "DOCUMENT_QUARANTINED": "high",
    "RAG_INJECTION_DETECTED": "high",
    "TOOL_DENIED": "medium",
    "STEP_UP_FAILED": "medium",
    "WEBHOOK_SUSPICIOUS": "high",
    "CONFIG_CHANGE": "medium",
    "PERMISSION_CHANGE": "high",
    "RATE_LIMIT_EXCEEDED": "low",
    "BOLA_SITE_DENIED": "high",
    "BOLA_EQUIPMENT_DENIED": "high",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_input(text: str) -> str:
    """Return a truncated SHA-256 hash of text for audit logging (not raw text)."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _redact_snippet(text: str) -> str:
    """Return a redacted snippet safe for audit logging."""
    if not text:
        return ""
    if len(text) <= REDACTED_SNIPPET_MAX_LENGTH:
        return text
    return text[:REDACTED_SNIPPET_MAX_LENGTH] + "..."


# ---------------------------------------------------------------------------
# Core audit writer
# ---------------------------------------------------------------------------


def write_security_audit(
    event_type: str,
    *,
    user: str = "system",
    source_ip: Optional[str] = None,
    input_hash: Optional[str] = None,
    snippet: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Write a security audit event to the existing audit system.

    Integrates with the singleton :class:`AuditLogger`:
        1. Logs via ``log_security_event()`` (JSON file + structured Loki output).
        2. Immediately flushes the buffer for all SECURITY_EVENTS.
        3. Sends a Telegram alert for ALERT_EVENTS via Sentry alert_notifier.

    Args:
        event_type: One of :data:`SECURITY_EVENTS` (validated but not enforced).
        user: User ID or ``"system"`` for automated events.
        source_ip: Client IP address (if available).
        input_hash: Pre-computed hash of the triggering input.
        snippet: Redacted snippet for context (will be truncated).
        metadata: Arbitrary additional context.

    Returns:
        The audit log entry ID.
    """
    if event_type not in SECURITY_EVENTS:
        logger.warning("write_security_audit called with unknown event_type: %s", event_type)

    severity = _EVENT_SEVERITY.get(event_type, "info")
    safe_snippet = _redact_snippet(snippet or "")

    # Build metadata dict
    event_metadata: dict[str, Any] = {
        "security_event": True,
        "input_hash": input_hash or "",
        "snippet": safe_snippet,
        **(metadata or {}),
    }

    # 1. Write via existing AuditLogger singleton
    try:
        from app.services.audit_logger import AuditLogger

        audit_logger = AuditLogger()
        entry_id = audit_logger.log_security_event(
            event_type=event_type,
            severity=severity,
            user=user,
            source_ip=source_ip,
            result=_severity_to_result(severity),
            metadata=event_metadata,
        )
    except Exception as exc:
        logger.error("Failed to write security audit event %s: %s", event_type, exc)
        entry_id = ""

    # 2. Immediate flush for all security events
    if event_type in SECURITY_EVENTS:
        try:
            from app.services.audit_logger import AuditLogger

            AuditLogger().flush()
        except Exception as exc:
            logger.error("Failed to flush audit buffer after %s: %s", event_type, exc)

    # 3. Telegram alert for critical events
    if event_type in ALERT_EVENTS:
        _send_telegram_alert(event_type, severity, user, source_ip, safe_snippet)

    return entry_id


def _severity_to_result(severity: str):
    """Map severity string to AuditResultType for the existing logger."""
    from app.models.audit_log import AuditResultType

    if severity in ("critical", "high"):
        return AuditResultType.BLOCKED
    if severity == "medium":
        return AuditResultType.WARNING
    return AuditResultType.SUCCESS


def _send_telegram_alert(
    event_type: str,
    severity: str,
    user: str,
    source_ip: Optional[str],
    snippet: str,
) -> None:
    """Send a Telegram alert for critical security events via Sentry.

    Uses the existing alert_notifier singleton. Failures are logged
    but never raise — audit writing must not be blocked by notification
    failures.
    """
    try:
        from app.services.sentry_integration.alert_notifier import alert_notifier

        alert_data = {
            "severity": "critical" if severity in ("critical", "high") else "warning",
            "equipment_code": "SENTINEL-SECURITY",
            "equipment_type": "security",
            "equipment_name": "Security Module",
            "site_name": "SENTINEL",
            "zone_name": "System",
            "message": (
                f"Security event: {event_type}\n"
                f"User: {user}\n"
                f"IP: {source_ip or 'unknown'}\n"
                f"Detail: {snippet[:120] if snippet else 'N/A'}"
            ),
        }

        alert_notifier.send_alert_sync(alert_data)
    except Exception as exc:
        logger.warning("Failed to send Telegram alert for %s: %s", event_type, exc)


# ---------------------------------------------------------------------------
# Convenience wrappers for common event types
# ---------------------------------------------------------------------------


def audit_prompt_guard_block(
    text: str,
    score: float,
    source: str = "direct",
    user: str = "system",
    source_ip: Optional[str] = None,
) -> str:
    """Audit a prompt guard block event."""
    return write_security_audit(
        "PROMPT_GUARD_BLOCK",
        user=user,
        source_ip=source_ip,
        input_hash=_hash_input(text),
        snippet=_redact_snippet(text),
        metadata={"score": score, "source": source},
    )


def audit_prompt_guard_rewrite(
    text: str,
    score: float,
    source: str = "direct",
    user: str = "system",
    source_ip: Optional[str] = None,
) -> str:
    """Audit a prompt guard rewrite event."""
    return write_security_audit(
        "PROMPT_GUARD_REWRITE",
        user=user,
        source_ip=source_ip,
        input_hash=_hash_input(text),
        snippet=_redact_snippet(text),
        metadata={"score": score, "source": source},
    )


def audit_output_filter_block(
    redactions: list[str],
    user: str = "system",
) -> str:
    """Audit an output filter block (e.g. system prompt leak)."""
    return write_security_audit(
        "OUTPUT_FILTER_BLOCK",
        user=user,
        metadata={"redactions": redactions},
    )


def audit_secret_detected(
    redaction_type: str,
    user: str = "system",
) -> str:
    """Audit a detected secret in output."""
    return write_security_audit(
        "SECRET_DETECTED",
        user=user,
        metadata={"redaction_type": redaction_type},
    )


def audit_document_quarantined(
    file_hash: str,
    reason: str,
    user: str = "system",
) -> str:
    """Audit a quarantined document upload."""
    return write_security_audit(
        "DOCUMENT_QUARANTINED",
        user=user,
        metadata={"file_hash": file_hash, "reason": reason},
    )


def audit_tool_denied(
    tool_name: str,
    reason: str,
    user: str = "system",
) -> str:
    """Audit a denied tool execution."""
    return write_security_audit(
        "TOOL_DENIED",
        user=user,
        metadata={"tool_name": tool_name, "reason": reason},
    )


def audit_step_up_failed(
    user: str,
    device_id: str,
    source_ip: Optional[str] = None,
) -> str:
    """Audit a failed step-up authentication attempt."""
    return write_security_audit(
        "STEP_UP_FAILED",
        user=user,
        source_ip=source_ip,
        metadata={"device_id": device_id},
    )


def audit_webhook_suspicious(
    webhook_type: str,
    reason: str,
    source_ip: Optional[str] = None,
) -> str:
    """Audit a suspicious webhook request."""
    return write_security_audit(
        "WEBHOOK_SUSPICIOUS",
        source_ip=source_ip,
        metadata={"webhook_type": webhook_type, "reason": reason},
    )


def audit_config_change(
    setting_key: str,
    user: str,
    source_ip: Optional[str] = None,
) -> str:
    """Audit a configuration change."""
    return write_security_audit(
        "CONFIG_CHANGE",
        user=user,
        source_ip=source_ip,
        metadata={"setting_key": setting_key},
    )


def audit_rate_limit_exceeded(
    path: str,
    source_ip: Optional[str] = None,
) -> str:
    """Audit a rate limit exceeded event."""
    return write_security_audit(
        "RATE_LIMIT_EXCEEDED",
        source_ip=source_ip,
        metadata={"path": path},
    )


def audit_bola_site_denied(
    user_id: str,
    email: str,
    role: str,
    site_id: str,
    path: str,
    method: str = "GET",
    source_ip: Optional[str] = None,
) -> str:
    """Audit a BOLA site access denial.

    Emitted when a user attempts to access a site they are not authorized for.
    Repeated events from the same user/IP may indicate probing.
    """
    return write_security_audit(
        "BOLA_SITE_DENIED",
        user=user_id,
        source_ip=source_ip,
        metadata={
            "email": email,
            "role": role,
            "target_site": site_id,
            "endpoint": path,
            "method": method,
        },
    )


def audit_bola_equipment_denied(
    user_id: str,
    email: str,
    role: str,
    equipment_code: str,
    derived_site: str,
    path: str,
    method: str = "GET",
    source_ip: Optional[str] = None,
) -> str:
    """Audit a BOLA equipment access denial.

    Emitted when a user attempts to access equipment belonging to a site
    they are not authorized for. The site is derived from the equipment code.
    """
    return write_security_audit(
        "BOLA_EQUIPMENT_DENIED",
        user=user_id,
        source_ip=source_ip,
        metadata={
            "email": email,
            "role": role,
            "target_equipment": equipment_code,
            "derived_site": derived_site,
            "endpoint": path,
            "method": method,
        },
    )
