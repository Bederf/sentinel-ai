r"""Bridge from Recommendation lifecycle to alert_notifier delivery.

Converts recommendation transitions into alert payloads compatible with
alert_notifier.send_alert_sync(). All guard logic (module-active, FM-chat-ID,
cooldown) is handled by alert_notifier — this service only builds the payload.

IMPORTANT: alert_notifier sanitizes Telegram markdown characters (*, {}, [], !,
#, \) for shell safety. Use plain text only — no markdown formatting.
"""

import logging
from typing import Any

from app.services.sentry_integration.alert_notifier import alert_notifier

logger = logging.getLogger(__name__)


class RecommendationNotifier:
    """Translates recommendation lifecycle events to alert_notifier payloads.

    Notification failure is non-fatal — the recommendation state transition
    commits regardless. Exceptions are caught and logged as warnings.
    """

    def build_alert_payload(
        self,
        *,
        recommendation_id: str,
        site_id: str,
        target_equipment: str,
        action: dict[str, Any],
        reason: str,
        risk_level: str,
        site_name: str,
        equipment_code: str,
        equipment_type: str,
        equipment_name: str,
        zone_name: str,
        severity: str,
        tier: int,
        execution_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build alert payload matching alert_notifier.send_alert_sync() contract.

        The caller resolves site_name, equipment_code, equipment_type,
        equipment_name, and zone_name before calling this. If resolution fails,
        pass ``"(unknown)"`` — never raise.

        Plain text only (no Telegram markdown). alert_notifier sanitizes
        ``*{}[]!#\\`` characters which would strip markdown formatting silently.
        """
        if tier == 2:
            msg = (
                f"Approval needed: Set {action.get('point', '?')} to "
                f"{action.get('value', '?')} on {equipment_code}. "
                f"Reason: {reason}"
            )
        elif tier == 3:
            new_state = "?"
            if execution_result and execution_result.get("success"):
                old_val = execution_result.get("previous_value", "?")
                new_val = execution_result.get("target_value", "?")
                point = execution_result.get("control_point", "?")
                new_state = f"{point}: {old_val} -> {new_val}"
            msg = f"Autonomous action applied: {equipment_code} -- {new_state}. Reason: {reason}"
        else:
            msg = reason or "Recommendation notification"

        return {
            "id": recommendation_id,
            "site_name": site_name or site_id,
            "zone_name": zone_name or "(unknown)",
            "equipment_name": equipment_name or equipment_code,
            "equipment_code": equipment_code,
            "equipment_type": equipment_type,
            "severity": severity,
            "message": msg,
        }

    def notify_tier2_awaiting_approval(
        self,
        *,
        recommendation_id: str,
        site_id: str,
        target_equipment: str,
        action: dict[str, Any],
        reason: str,
        risk_level: str,
        site_name: str,
        equipment_code: str,
        equipment_type: str,
        equipment_name: str,
        zone_name: str,
    ) -> bool:
        """Fire Tier 2 awaiting-approval notification to FM group.

        Called inside ``request_approval_node()`` after the approval request is
        formatted and before ``needs_input=True`` is set. The recommendation is
        already persisted as PENDING — the graph pauses for human input.

        All guard logic (module-active, FM-chat-ID, cooldown) is handled by
        ``alert_notifier.send_alert_sync()``. This function only builds and
        sends the payload.

        Cooldown caveat: the cooldown is keyed by ``equipment_code:severity``.
        If two different recommendations for the same equipment both enter Tier 2
        within the cooldown window (default 5 min), the second notification is
        suppressed. This is a rare edge case accepted for v1.

        Returns:
            True if sent or guard denied silently (module inactive, FM chat
            unconfigured, cooldown). False if alert_notifier had a delivery
            error — caller logs and continues, state transition unaffected.
        """
        severity = self._risk_to_severity(risk_level)
        payload = self.build_alert_payload(
            recommendation_id=recommendation_id,
            site_id=site_id,
            target_equipment=target_equipment,
            action=action,
            reason=reason,
            risk_level=risk_level,
            site_name=site_name,
            equipment_code=equipment_code,
            equipment_type=equipment_type,
            equipment_name=equipment_name,
            zone_name=zone_name,
            severity=severity,
            tier=2,
        )
        logger.info(
            "Sending Tier 2 approval notification for rec-%s to FM group",
            recommendation_id[:8],
        )
        success = alert_notifier.send_alert_sync(payload)
        if not success:
            logger.warning(
                "Tier 2 notification did not send for rec-%s "
                "(alert_notifier returned False — guard denied or delivery failed). "
                "Recommendation state is committed; operator should check FM group.",
                recommendation_id[:8],
            )
        return success

    def notify_tier3_auto_executed(
        self,
        *,
        recommendation_id: str,
        site_id: str,
        target_equipment: str,
        action: dict[str, Any],
        reason: str,
        risk_level: str,
        execution_result: dict[str, Any],
        site_name: str,
        equipment_code: str,
        equipment_type: str,
        equipment_name: str,
        zone_name: str,
    ) -> bool:
        """Fire Tier 3 auto-execution notification to FM group.

        Called in ``auto_execute_recommendation()`` after successful device
        write, replacing the bespoke ``_send_auto_execution_notification()``
        call. All AEGIS gating (quality gate, onboarding phase) has already
        passed by this point.

        Acknowledging the notification (via the rec:review callback in the old
        bespoke path) is NOT included in v1. The FM group receives information,
        not an interactive component. Acknowledge can be added as a follow-up.

        Returns:
            True if sent, False if alert_notifier failed (caller logs and
            continues — execution already committed).
        """
        severity = self._risk_to_severity(risk_level)
        payload = self.build_alert_payload(
            recommendation_id=recommendation_id,
            site_id=site_id,
            target_equipment=target_equipment,
            action=action,
            reason=reason,
            risk_level=risk_level,
            site_name=site_name,
            equipment_code=equipment_code,
            equipment_type=equipment_type,
            equipment_name=equipment_name,
            zone_name=zone_name,
            severity=severity,
            tier=3,
            execution_result=execution_result,
        )
        logger.info(
            "Sending Tier 3 execution notification for rec-%s to FM group",
            recommendation_id[:8],
        )
        success = alert_notifier.send_alert_sync(payload)
        if not success:
            logger.warning(
                "Tier 3 execution notification failed for rec-%s (alert_notifier returned False). Execution committed.",
                recommendation_id[:8],
            )
        return success

    @staticmethod
    def _risk_to_severity(risk_level: str) -> str:
        """Map recommendation risk_level to alert severity."""
        mapping = {
            "low": "info",
            "medium": "warning",
            "high": "critical",
            "critical": "critical",
        }
        return mapping.get(risk_level.strip().lower(), "info")
