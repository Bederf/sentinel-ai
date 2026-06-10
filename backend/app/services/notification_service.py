"""
NotificationService — orchestrates multi-channel notification delivery.

Phase 102: Routes notifications to technicians via their enabled channels (Telegram, WhatsApp, SMS).
Respects technician preferences: quiet hours, alert level thresholds, emergency override.
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from ..database.repositories.notification_repository import NotificationRepository
from ..models.notification import (
    AlertLevel,
    ChannelType,
    NotificationDeliveryLog,
    NotificationStatus,
    TechnicianNotificationChannel,
)
from .notification_providers import (
    BulkSMSProvider,
    TelegramProvider,
    WhatsAppProvider,
)
from .notification_providers.base_provider import NotificationResult

logger = logging.getLogger(__name__)


class NotificationService:
    """Orchestrates multi-channel technician notification delivery."""

    def __init__(self):
        """Initialize the notification service."""
        # Initialize repository for database access
        self.notification_repo = NotificationRepository()

        # Initialize providers
        self.providers = {
            ChannelType.TELEGRAM: TelegramProvider(),
            ChannelType.WHATSAPP: WhatsAppProvider(),
            ChannelType.SMS: BulkSMSProvider(),
        }

    async def initialize(self):
        """Initialize notification service (no-op, providers ready from __init__)."""
        pass

    async def notify_technician(
        self,
        technician_id: UUID,
        title: str,
        body: str,
        alert_level: AlertLevel = AlertLevel.WARNING,
        work_order_id: UUID | None = None,
        notification_type: str = "work_order_assigned",
    ) -> dict:
        """Send notification to technician via enabled channels.

        Respects technician preferences: quiet hours, alert thresholds, emergency override.
        Sends simultaneously to ALL enabled channels (not cascade/fallback).

        Args:
            technician_id: UUID of technician to notify
            title: Notification title
            body: Notification body/message
            alert_level: Severity level (info, warning, critical)
            work_order_id: Associated work order ID (optional)
            notification_type: Type of notification (work_order_assigned, alert, update, test)

        Returns:
            {
                "success": bool,
                "channels_sent": [ChannelType],
                "channels_failed": [ChannelType],
                "deliveries": [NotificationDeliveryLog],
                "errors": {ChannelType: error_message},
            }
        """
        result: dict = {
            "success": True,
            "channels_sent": [],
            "channels_failed": [],
            "deliveries": [],
            "errors": {},
        }

        try:
            # Fetch technician preferences
            preferences = await self.notification_repo.get_notification_preferences(technician_id)
            if not preferences:
                logger.warning(f"No notification preferences found for technician {technician_id}")
                result["success"] = False
                result["errors"]["system"] = "No preferences configured"
                return result

            # Check if notification should be sent (respects quiet hours, alert levels)
            if not preferences.should_notify_now(alert_level):
                logger.info(
                    f"Notification suppressed for technician {technician_id} "
                    f"(quiet hours active, alert_level={alert_level})"
                )
                result["success"] = False
                result["errors"]["system"] = "Notification suppressed by quiet hours"
                return result

            # Fetch enabled channels
            enabled_channels = await self.notification_repo.get_notification_channels(
                technician_id,
                channel_types=preferences.enabled_channels,
            )
            if not enabled_channels:
                logger.warning(f"No notification channels configured for technician {technician_id}")
                result["success"] = False
                result["errors"]["system"] = "No channels configured"
                return result

            # Send to all enabled channels simultaneously (not cascade)
            delivery_tasks = []
            for channel in enabled_channels:
                task = self._send_to_channel(
                    channel=channel,
                    technician_id=technician_id,
                    title=title,
                    body=body,
                    work_order_id=work_order_id,
                    notification_type=notification_type,
                )
                delivery_tasks.append(task)

            # Execute all sends concurrently
            deliveries = []
            for channel_delivery in delivery_tasks:
                channel_type, delivery_log, error = await channel_delivery
                deliveries.append((channel_type, delivery_log, error))

            # Collect results
            for channel_type, delivery_log, error in deliveries:
                if error:
                    result["channels_failed"].append(channel_type)
                    result["errors"][channel_type] = error
                else:
                    result["channels_sent"].append(channel_type)
                    result["deliveries"].append(delivery_log)

            # Overall success: at least one channel succeeded
            result["success"] = bool(result["channels_sent"])
            return result

        except Exception as e:
            logger.error(f"NotificationService error for technician {technician_id}: {e}")
            result["success"] = False
            result["errors"]["system"] = str(e)
            return result

    async def broadcast_alert(
        self,
        title: str,
        body: str,
        alert_level: AlertLevel = AlertLevel.CRITICAL,
        notification_type: str = "plant_alert",
    ) -> dict:
        """Broadcast alert to all technicians with plant alert preferences.

        For deployments without technician DB configured, falls back to
        sending directly via each enabled provider to the default chat/number.

        Returns:
            {"success": bool, "recipients_notified": int, "errors": [...]}
        """
        result: dict = {"success": False, "recipients_notified": 0, "errors": []}

        # Try per-technician routing first
        try:
            tech_ids = await self.notification_repo.get_alert_subscribers(
                alert_level=alert_level,
                notification_type=notification_type,
            )
            if tech_ids:
                for tech_id in tech_ids:
                    tech_result = await self.notify_technician(
                        technician_id=tech_id,
                        title=title,
                        body=body,
                        alert_level=alert_level,
                        notification_type=notification_type,
                    )
                    if tech_result["success"]:
                        result["recipients_notified"] += 1
                    else:
                        result["errors"].extend(tech_result.get("errors", {}).values())
                # If no per-technician channel succeeded, fall through to
                # default provider routing (telegram_alert_chat_id /
                # twilio_whatsapp_to) instead of returning hard-fail.
                if result["recipients_notified"] > 0:
                    result["success"] = True
                    return result
        except Exception as e:
            logger.warning(f"Technician lookup failed, falling back to direct send: {e}")

        # Fallback: send directly via each enabled provider to default recipient
        for channel_type, provider in self.providers.items():
            if not provider.is_enabled():
                continue
            try:
                default_recipient = self._get_default_recipient(channel_type)
                if not default_recipient:
                    continue
                send_result = await provider.send(default_recipient, title, body)
                if send_result.success:
                    result["recipients_notified"] += 1
            except Exception as e:
                result["errors"].append(f"{channel_type}: {e}")

        result["success"] = result["recipients_notified"] > 0
        return result

    async def send_alert_direct(
        self,
        title: str,
        body: str,
        alert_level: AlertLevel = AlertLevel.WARNING,
    ) -> dict:
        """Send an alert directly via TelegramProvider (bypasses technician lookup).

        For infrastructure alerts (sensor offline, data freshness) where no
        technician_id is available. Sends to the default FM chat ID.

        Returns:
            {"success": bool, "error": str|None}
        """
        from app.config.settings import settings

        telegram_to = (
            str(getattr(settings, "sentry_fm_chat_id", "") or "").strip()
            or str(getattr(settings, "telegram_alert_chat_id", "") or "").strip()
        )
        if not telegram_to:
            return {"success": False, "error": "no_telegram_chat_id_configured"}

        provider = self.providers.get(ChannelType.TELEGRAM)
        if not provider or not provider.is_enabled():
            return {"success": False, "error": "telegram_not_enabled"}

        try:
            send_result = await provider.send(telegram_to, title, body)
            return {"success": bool(send_result.success), "error": getattr(send_result, "error_message", None)}
        except Exception as e:
            logger.warning(f"[NOTIFY] send_alert_direct failed: {e}")
            return {"success": False, "error": str(e)}

    def _get_default_recipient(self, channel_type: ChannelType) -> str:
        """Get default recipient for a channel when no technician DB available."""
        from app.config.settings import settings

        if channel_type == ChannelType.TELEGRAM:
            return settings.telegram_alert_chat_id
        elif channel_type == ChannelType.WHATSAPP:
            return settings.twilio_whatsapp_to.replace("whatsapp:", "") if settings.twilio_whatsapp_to else ""
        return ""

    async def _send_to_channel(
        self,
        channel: TechnicianNotificationChannel,
        technician_id: UUID,
        title: str,
        body: str,
        work_order_id: UUID | None,
        notification_type: str,
    ) -> tuple:
        """Send notification to single channel and log delivery.

        Returns:
            (channel_type, delivery_log, error_message)
        """
        channel_type = channel.channel_type
        recipient_identifier = channel.get_contact_identifier()

        # Get provider for this channel
        provider = self.providers.get(channel_type)
        if not provider:
            error_msg = f"Provider not found for channel {channel_type}"
            logger.error(error_msg)
            return (channel_type, None, error_msg)

        # Check if provider is enabled
        if not provider.is_enabled():
            error_msg = f"Provider {provider.provider_name} not configured"
            logger.warning(error_msg)
            return (channel_type, None, error_msg)

        # Create delivery log entry (initial state: PENDING)
        delivery_log = NotificationDeliveryLog(
            id=UUID(int=0),  # Will be set by repository
            work_order_id=work_order_id,
            technician_id=technician_id,
            notification_type=notification_type,
            title=title,
            body=body,
            channel_type=channel_type,
            recipient_identifier=recipient_identifier,
            status=NotificationStatus.PENDING,
            provider=provider.provider_name,
        )

        try:
            # Send via provider
            notification_result: NotificationResult = await provider.send(
                recipient=recipient_identifier,
                title=title,
                body=body,
            )

            # Update delivery log with result
            if notification_result.success:
                delivery_log.status = NotificationStatus.SENT
                delivery_log.external_message_id = notification_result.message_id
                delivery_log.sent_at = datetime.utcnow()
                delivery_log.provider_response = notification_result.provider_response or {}
                logger.info(
                    f"Notification sent to {channel_type} for technician {technician_id} "
                    f"(provider: {provider.provider_name})"
                )
                error = None
            else:
                delivery_log.status = NotificationStatus.FAILED
                delivery_log.error_code = notification_result.error_code
                delivery_log.error_message = notification_result.error_message
                delivery_log.provider_response = notification_result.provider_response or {}
                error = notification_result.error_message
                logger.warning(f"Notification send failed for {channel_type} to technician {technician_id}: {error}")

            # Persist delivery log
            created_log = await self.notification_repo.create_delivery_log(delivery_log)
            return (channel_type, created_log, error)

        except Exception as e:
            delivery_log.status = NotificationStatus.FAILED
            delivery_log.error_code = "exception"
            delivery_log.error_message = str(e)
            logger.error(f"Error sending notification to {channel_type} for technician {technician_id}: {e}")
            created_log = await self.notification_repo.create_delivery_log(delivery_log)
            return (channel_type, created_log, str(e))

    async def test_provider_connection(self, channel_type: ChannelType) -> bool:
        """Test if a provider is configured and reachable.

        Args:
            channel_type: Channel to test (TELEGRAM, WHATSAPP, SMS)

        Returns:
            True if provider is ready, False otherwise
        """
        provider = self.providers.get(channel_type)
        if not provider:
            logger.error(f"No provider found for channel {channel_type}")
            return False

        try:
            return await provider.test_connection()
        except Exception as e:
            logger.error(f"Provider test failed for {channel_type}: {e}")
            return False

    def get_provider_status(self) -> dict:
        """Get configuration and readiness status of all providers.

        Returns:
            {
                "telegram": {"enabled": bool, "name": str},
                "whatsapp": {"enabled": bool, "name": str},
                "sms": {"enabled": bool, "name": str},
            }
        """
        return {
            channel.value: {
                "enabled": self.providers[channel].is_enabled(),
                "name": self.providers[channel].provider_name,
            }
            for channel in ChannelType
            if channel in self.providers
        }

    async def send_certified(
        self,
        *,
        site_id: str,
        recipient_telegram_id: str,
        title: str,
        message: str,
        alert_level: AlertLevel = AlertLevel.WARNING,
        reference_id: str | None = None,
        acknowledgement_timeout_minutes: int = 15,
        action_label: str = "✅ Acknowledged",
        callback_action: str = "ack",
    ) -> dict:
        """Send a certified notification requiring Telegram acknowledgement.

        Flow:
        1. Send message with inline [✅ Acknowledged] keyboard via TelegramProvider
        2. Log delivery to notification_delivery_log
        3. Schedule escalation if no acknowledgement within timeout
        4. Return notification_id for tracking

        Args:
            site_id: Site context
            recipient_telegram_id: Telegram chat ID
            title: Notification title
            message: Notification body
            alert_level: Severity
            reference_id: Optional reference (work_order_id, alert_id, etc.)
            acknowledgement_timeout_minutes: Minutes before escalation

        Returns:
            {"success": bool, "notification_id": str, "error": str|None}
        """
        from uuid import uuid4

        notification_id = str(uuid4())
        provider = self.providers[ChannelType.TELEGRAM]

        if not provider.is_enabled():
            return {"success": False, "notification_id": notification_id, "error": "telegram_not_enabled"}

        # Build inline keyboard with acknowledgement button
        from app.services.telegram_message_sender import InlineButton, InlineKeyboard, get_telegram_sender

        if callback_action == "ack":
            callback_data = f"ack:{notification_id}:{reference_id or ''}"
        elif reference_id and reference_id not in callback_action:
            callback_data = f"{callback_action}:{reference_id}"
        else:
            callback_data = callback_action

        keyboard = InlineKeyboard(rows=[[InlineButton(label=action_label, callback_data=callback_data)]])

        # Send via Telegram sender (supports inline keyboard)
        sender = get_telegram_sender()
        try:
            result = await sender.send_text(
                chat_id=recipient_telegram_id,
                text=f"<b>{title}</b>\n\n{message}",
                keyboard=keyboard,
            )
            msg_id = result.get("result", {}).get("message_id") if result.get("ok") else None
        except Exception as e:
            logger.warning(f"[CERTIFIED] Telegram send failed for {recipient_telegram_id}: {e}")
            msg_id = None
            telegram_error = str(e)
        else:
            telegram_error = None

        # Log delivery
        try:
            delivery_log = NotificationDeliveryLog(
                id=uuid4(),
                technician_id=UUID("00000000-0000-0000-0000-000000000000"),  # system notifier
                notification_type="certified",
                channel_type=ChannelType.TELEGRAM,
                recipient_identifier=recipient_telegram_id,
                status=NotificationStatus.SENT if msg_id else NotificationStatus.FAILED,
                provider="telegram",
                external_message_id=msg_id,
                sent_at=datetime.utcnow(),
                error_message=telegram_error,
            )
            await self.notification_repo.create_delivery_log(delivery_log)
        except Exception as log_err:
            logger.warning(f"[CERTIFIED] Failed to log delivery: {log_err}")

        # Schedule escalation check (fire-and-forget, no reference needed)
        if msg_id:
            asyncio.create_task(  # noqa: RUF006
                self._check_acknowledgement(
                    notification_id=notification_id,
                    recipient_telegram_id=recipient_telegram_id,
                    title=title,
                    message=message,
                    timeout_minutes=acknowledgement_timeout_minutes,
                    reference_id=reference_id,
                )
            )

        return {
            "success": bool(msg_id),
            "notification_id": notification_id,
            "error": None if msg_id else "send_failed",
        }

    async def handle_work_order_request(
        self,
        callback_data: str,
        requested_by_telegram_id: str,
    ) -> dict:
        """Create a work order from an AI optimization recommendation callback."""
        if not callback_data.startswith("wo:"):
            return {"success": False, "error": "invalid_callback_data"}

        # callback_data format: wo:rec_id:{uuid} or wo:{uuid}
        recommendation_id = callback_data.split(":")[-1]

        try:
            from app.database.repositories.recommendation_repository import get_recommendation_repository
            from app.database.repositories.work_order_repository import get_work_order_repository
            from app.models.recommendation import RecommendationStatus

            rec_repo = get_recommendation_repository()
            work_order_repo = get_work_order_repository()
            rec = await rec_repo.get(recommendation_id)
            if not rec:
                return {"success": False, "error": "recommendation_not_found", "recommendation_id": recommendation_id}

            try:
                from app.database.supabase_client import get_supabase_client
                from app.models.module_registry import ModuleType
                from app.models.onboarding_phase import phase_allows
                from app.services.module_registry_service import module_registry

                try:
                    sb = get_supabase_client()
                    phase_result = (
                        sb.table("sites").select("onboarding_phase").eq("code", rec.site_id).limit(1).execute()
                    )
                    site_phase = (
                        (phase_result.data[0].get("onboarding_phase") or "commissioning")
                        if phase_result.data
                        else "commissioning"
                    )
                except Exception:
                    site_phase = "commissioning"

                if not phase_allows(site_phase, "recommendations_ui"):
                    return {
                        "success": False,
                        "error": "recommendations_not_visible_in_phase",
                        "recommendation_id": recommendation_id,
                        "site_id": rec.site_id,
                        "phase": site_phase,
                    }

                if not module_registry.is_module_active(rec.site_id, ModuleType.MAINTENANCE):
                    return {
                        "success": False,
                        "error": "maintenance_module_inactive",
                        "recommendation_id": recommendation_id,
                        "site_id": rec.site_id,
                    }
            except Exception as gate_err:
                logger.warning("[CERTIFIED] Maintenance module gate failed for %s: %s", rec.site_id, gate_err)
                return {
                    "success": False,
                    "error": "maintenance_module_gate_failed",
                    "recommendation_id": recommendation_id,
                    "site_id": rec.site_id,
                }

            equipment_code = rec.target_equipment
            action = rec.action or {}
            action_point = action.get("point")
            action_value = action.get("value")

            if equipment_code and action_point and action_value is not None:
                # Tier 1: Exact dedup — same equipment + point + value → block duplicate
                exact_match = await work_order_repo.get_open_for_equipment_action(
                    equipment_code=equipment_code,
                    action_point=action_point,
                    action_value=str(action_value),
                )
                if exact_match:
                    return {
                        "success": True,
                        "action": "duplicate_work_order_exists",
                        "recommendation_id": recommendation_id,
                        "work_order": exact_match,
                    }

                # Tier 2: Same equipment + same point (different value) → allow
                # (conditions changed, new target is valid)
                open_wos = await work_order_repo.get_open_work_orders_for_equipment(equipment_code)
                if open_wos:
                    return {
                        "success": True,
                        "action": "open_work_order_exists",
                        "recommendation_id": recommendation_id,
                        "work_order": open_wos[0],
                    }
            elif equipment_code:
                # No specific point/value — fall back to equipment-level dedup (legacy)
                open_wos = await work_order_repo.get_open_work_orders_for_equipment(equipment_code)
                if open_wos:
                    return {
                        "success": True,
                        "action": "open_work_order_exists",
                        "recommendation_id": recommendation_id,
                        "work_order": open_wos[0],
                    }

            impact = rec.expected_impact or {}
            unit = impact.get("unit", "")
            current_value = impact.get("current_value")
            recommended_value = impact.get("recommended_value", action_value)
            current_line = f"Current value: {current_value}{unit}\n" if current_value is not None else ""

            description = (
                f"Created from SENTINEL AI advisory recommendation {recommendation_id}.\n\n"
                f"Equipment: {equipment_code or 'Unknown'}\n"
                f"Action: Set {action_point or 'recommended adjustment'} to {recommended_value}{unit}\n"
                f"{current_line}"
                f"Goal: {(rec.profile or 'optimization').replace('_', ' ').title()}\n"
                f"Confidence: {round((rec.confidence_score or rec.get_numeric_confidence()) * 100)}%\n\n"
                f"Reason:\n{rec.reason}"
            )

            # Lookup technician by specialty BEFORE creating the WO (so assigned_to is persisted)
            tech_telegram_id = None
            tech_email = None
            tech_name = None
            assigned_to = None
            assigned_team = None
            try:
                from app.database.repositories.technician_repository import TechnicianRepository

                tech_repo = TechnicianRepository()
                technician = await tech_repo.get_technician_for_equipment_code(equipment_code)
                if technician:
                    tech_name = technician.get("name", "Unassigned")
                    tech_telegram_id = technician.get("telegram_id") or technician.get("telegram_chat_id")
                    tech_email = technician.get("email")
                    assigned_to = tech_name
                    assigned_team = technician.get("specialty")
            except Exception as tech_err:
                logger.warning("[CERTIFIED] Could not find technician for %s: %s", equipment_code, tech_err)

            created_wo = await work_order_repo.create_work_order(
                {
                    "title": f"SENTINEL Advisory Action: {equipment_code or 'Equipment'}",
                    "description": description,
                    "priority": "medium",
                    "status": "scheduled",
                    "equipment_code": equipment_code,
                    "site_id": rec.site_id,
                    "created_by": f"telegram:{requested_by_telegram_id}",
                    "milestone_status": "assigned",
                    "estimated_duration_hours": 1,
                    "assigned_to": assigned_to,
                    "assigned_team": assigned_team,
                    "action_point": action_point,
                    "action_value": str(action_value) if action_value is not None else None,
                    "recommendation_id": recommendation_id,
                }
            )

            if not created_wo:
                return {"success": False, "error": "work_order_create_failed", "recommendation_id": recommendation_id}

            rec.status = RecommendationStatus.APPROVED
            rec.approved_by = f"telegram:{requested_by_telegram_id}"
            rec.approved_at = datetime.utcnow()
            rec.approval_reason = f"Work order created from Telegram advisory button: {created_wo.get('code')}"
            rec.external_ticket_id = created_wo.get("code")
            try:
                await rec_repo.update(recommendation_id, rec)
            except Exception as update_err:
                logger.warning("[CERTIFIED] Work order created but recommendation update failed: %s", update_err)

            logger.info(
                "[CERTIFIED] Work order %s created from recommendation %s by %s",
                created_wo.get("code"),
                recommendation_id,
                requested_by_telegram_id,
            )

            # Notify assigned technician via WorkOrderNotifier (technician bot, not FM bot)
            wo_code = created_wo.get("code")
            priority = created_wo.get("priority", "medium")
            if wo_code:
                from app.services.sentry_integration.work_order_notifier import WorkOrderNotifier

                notifier = WorkOrderNotifier()
                wo_notify_data = {
                    "work_order_id": created_wo.get("id"),
                    "code": wo_code,
                    "site_id": rec.site_id,
                    "equipment_code": equipment_code,
                    "equipment_name": equipment_code,
                    "criticality": (priority or "medium").upper(),
                    "service_type": "callout",
                    "technician_id": tech_telegram_id,
                    "technician_name": tech_name or "Pending",
                    "description": description,
                    "technician_email": tech_email,
                    "create_service_record": False,
                }
                asyncio.create_task(notifier.notify_technician(wo_notify_data))

            return {
                "success": True,
                "action": "work_order_created",
                "recommendation_id": recommendation_id,
                "work_order": created_wo,
                "equipment_code": equipment_code,
            }
        except Exception as e:
            logger.warning("[CERTIFIED] Failed to create work order from %s: %s", recommendation_id, e)
            return {"success": False, "error": str(e), "recommendation_id": recommendation_id}

    async def handle_prediction_work_order_request(
        self,
        callback_data: str,
        prediction_id: str,
        requested_by_telegram_id: str,
    ) -> dict:
        """Create a work order from a prediction Telegram notification button press.

        Uses the workflow trigger engine (on_prediction_critical) to create
        the work order, which handles dedup against existing open work orders.
        """

        try:
            from app.database.repositories.prediction_repository import get_prediction_repository
            from app.services.workflow_triggers import get_trigger_engine

            pred_repo = get_prediction_repository()
            prediction = pred_repo.get_by_id(prediction_id)

            if not prediction:
                return {"success": False, "error": "prediction_not_found", "prediction_id": prediction_id}

            # Get equipment
            equipment_id = prediction.get("equipment_id")
            equipment_code = None
            equipment_health = 50

            if equipment_id:
                from app.database.repositories.equipment_repository import get_equipment_repository

                eq_repo = get_equipment_repository()
                equipment = eq_repo.get_by_uuid(equipment_id)
                if equipment:
                    equipment_code = equipment.get("code")
                    equipment_health = equipment.get("health_score", 50)

            # Get site_id from prediction
            site_id = prediction.get("site_id")
            if not site_id and equipment:
                site_id = equipment.get("site_id")

            # Gate check: maintenance module must be active
            try:
                from app.database.supabase_client import get_supabase_client
                from app.models.module_registry import ModuleType
                from app.models.onboarding_phase import phase_allows
                from app.services.module_registry_service import module_registry

                try:
                    sb = get_supabase_client()
                    phase_result = sb.table("sites").select("onboarding_phase").eq("code", site_id).limit(1).execute()
                    site_phase = (
                        (phase_result.data[0].get("onboarding_phase") or "commissioning")
                        if phase_result.data
                        else "commissioning"
                    )
                except Exception:
                    site_phase = "commissioning"

                if not phase_allows(site_phase, "recommendations_ui"):
                    return {
                        "success": False,
                        "error": "recommendations_not_visible_in_phase",
                        "prediction_id": prediction_id,
                        "site_id": site_id,
                        "phase": site_phase,
                    }

                if not module_registry.is_module_active(site_id, ModuleType.MAINTENANCE):
                    return {
                        "success": False,
                        "error": "maintenance_module_inactive",
                        "prediction_id": prediction_id,
                        "site_id": site_id,
                    }
            except Exception as gate_err:
                logger.warning("[PRED-WO] Maintenance module gate failed for %s: %s", site_id, gate_err)
                return {
                    "success": False,
                    "error": "maintenance_module_gate_failed",
                    "prediction_id": prediction_id,
                    "site_id": site_id,
                }

            # Use the workflow trigger engine (same path as auto-trigger for critical predictions)
            engine = get_trigger_engine()
            result = await engine.on_prediction_critical(
                equipment_id=equipment_id or "",
                prediction_id=str(prediction.get("id", "")),
                prediction_code=prediction.get("code", ""),
                health_score=equipment_health,
                probability_percent=prediction.get("probability_percent", 0),
                equipment_code=equipment_code,
            )

            if result.success:
                created_wo = None
                if result.action_taken in ("created_work_order", "open_work_order_exists"):
                    # Extract work order info from result details
                    wo_id = result.details.get("work_order_id")
                    wo_code = result.details.get("work_order_code")
                    if wo_id:
                        from app.database.repositories.work_order_repository import get_work_order_repository

                        wo_repo = get_work_order_repository()
                        created_wo = wo_repo.get_by_id(wo_id)
                    if not created_wo and wo_code:
                        created_wo = {"code": wo_code, "id": wo_id}

                return {
                    "success": True,
                    "action": result.action_taken,
                    "prediction_id": prediction_id,
                    "work_order": created_wo,
                }
            else:
                return {
                    "success": False,
                    "error": result.action_taken or "trigger_failed",
                    "prediction_id": prediction_id,
                }

        except Exception as e:
            logger.warning("[PRED-WO] Failed to create work order from prediction %s: %s", prediction_id, e)
            return {"success": False, "error": str(e), "prediction_id": prediction_id}

    async def handle_prediction_acknowledge(
        self,
        callback_data: str,
        acknowledged_by_telegram_id: str,
    ) -> dict:
        """Handle [✅ Acknowledge] button press from a prediction Telegram notification.

        Records acknowledgement in notification_delivery_log and decision memory.
        """
        parts = callback_data.split(":")
        if len(parts) < 2 or parts[0] != "pred_ack":
            return {"success": False, "error": "invalid_callback_data"}

        prediction_id = parts[1]

        try:
            # Log acknowledgement
            await self.notification_repo.update_delivery_log_acknowledged(
                notification_id=prediction_id,
                acknowledged_by=acknowledged_by_telegram_id,
                acknowledged_at=datetime.utcnow(),
            )

            # Record in decision memory
            if prediction_id:
                try:
                    from app.services.decision_memory_service import get_decision_memory_service

                    dm = get_decision_memory_service()
                    await dm.record_decision(
                        equipment_id=None,
                        action="telegram_prediction_acknowledgement",
                        reason="Prediction acknowledged via Telegram button",
                        outcome_record={
                            "acknowledged_by": acknowledged_by_telegram_id,
                            "prediction_id": prediction_id,
                        },
                    )
                except Exception:
                    pass  # Decision memory is best-effort

            return {"success": True, "prediction_id": prediction_id}
        except Exception as e:
            logger.warning("[PRED-ACK] Failed to acknowledge prediction %s: %s", prediction_id, e)
            return {"success": False, "error": str(e), "prediction_id": prediction_id}

    async def handle_acknowledgement(
        self,
        callback_data: str,
        acknowledged_by_telegram_id: str,
    ) -> dict:
        """Handle [✅ Acknowledged] button press from Telegram.

        Called by the Telegram gateway when FM taps the inline button.
        1. Updates delivery log and cancels pending escalation.
        2. Records acknowledgement in decision memory for learning loop.
        3. Outcome verification (30-min telemetry check) runs via scheduled job.
        """
        parts = callback_data.split(":")
        if len(parts) < 2 or parts[0] != "ack":
            return {"success": False, "error": "invalid_callback_data"}

        notification_id = parts[1]
        reference_id = parts[2] if len(parts) > 2 else None

        try:
            await self.notification_repo.update_delivery_log_acknowledged(
                notification_id=notification_id,
                acknowledged_by=acknowledged_by_telegram_id,
                acknowledged_at=datetime.utcnow(),
            )

            # Record acknowledgement in decision memory (learning loop)
            if reference_id:
                try:
                    from app.services.decision_memory_service import get_decision_memory_service

                    dm = get_decision_memory_service()
                    await dm.record_decision(
                        equipment_id=reference_id,
                        action="telegram_acknowledgement",
                        reason="Acknowledged via Telegram — operator confirmed action taken",
                        outcome_record={
                            "acknowledged_by": acknowledged_by_telegram_id,
                            "notification_id": notification_id,
                        },
                    )
                except Exception as dm_err:
                    logger.warning(f"[CERTIFIED] Failed to record decision memory for {reference_id}: {dm_err}")

            logger.info(f"[CERTIFIED] Notification {notification_id} acknowledged by {acknowledged_by_telegram_id}")
            return {"success": True, "notification_id": notification_id, "reference_id": reference_id}
        except Exception as e:
            logger.warning(f"[CERTIFIED] Failed to record acknowledgement for {notification_id}: {e}")
            return {"success": False, "error": str(e)}

    async def _check_acknowledgement(
        self,
        notification_id: str,
        recipient_telegram_id: str,
        title: str,
        message: str,
        timeout_minutes: int,
        reference_id: str | None,
    ) -> None:
        """Wait for acknowledgement timeout, then escalate if not acknowledged."""

        await asyncio.sleep(timeout_minutes * 60)

        try:
            # Check if already acknowledged via notification_id lookup
            result = (
                self.notification_repo.client.table("notification_delivery_log")
                .select("id, acknowledged_at, escalated")
                .eq("notification_id", notification_id)
                .limit(1)
                .execute()
            )

            if not result.data:
                logger.warning(f"[CERTIFIED] Delivery log not found for {notification_id}")
                return

            row = result.data[0]
            if row.get("acknowledged_at") or row.get("escalated"):
                # Already acknowledged or escalated — nothing to do
                return

            logger.warning(
                f"[CERTIFIED] Notification {notification_id} unacknowledged after {timeout_minutes}min — escalating"
            )
            await self._escalate(
                notification_id=notification_id,
                recipient_telegram_id=recipient_telegram_id,
                title=title,
                message=message,
                reference_id=reference_id,
            )
        except Exception as e:
            logger.warning(f"[CERTIFIED] Escalation check failed for {notification_id}: {e}")

    async def _notify_technician(
        self,
        wo_code: str,
        equipment_code: str,
        tech_telegram_id: str | None,
        tech_email: str | None,
        tech_name: str | None,
        priority: str = "medium",
    ) -> None:
        """Send Telegram + email notification to the assigned technician.

        Mirrors slash_command_router._notify_technician for work orders created
        from AI advisory button presses.
        """
        # --- Telegram via sentry CLI ---
        if tech_telegram_id:
            from app.services.telegram_message_sender import get_telegram_sender

            sender = get_telegram_sender()
            assigned = tech_name or "Pending"
            msg = f"Work Order Created #{wo_code}\nAssigned: {assigned}\nPriority: {priority.upper()}"
            try:
                await sender.send_text(chat_id=str(tech_telegram_id), text=msg)
                logger.info("Telegram sent to %s for %s", tech_telegram_id, wo_code)
            except Exception as exc:
                logger.warning("Telegram notification failed for %s: %s", wo_code, exc)

        # --- Email via SMTP (workorder@sentinel-ai.co.za) ---
        if tech_email:
            try:
                from app.services.email_reply_service import get_email_reply_service

                svc = get_email_reply_service()
                if svc.is_configured():
                    subject = f"SENTINEL {wo_code} — Work Order"
                    result = await svc.send_reply(
                        to_email=tech_email,
                        to_name=tech_name,
                        subject=subject,
                        body_plain=f"Work Order Created #{wo_code}\nAssigned: {tech_name or 'Pending'}\nPriority: {priority.upper()}\n\nPlease acknowledge receipt.",
                        body_html=None,
                    )
                    if result.sent:
                        logger.info("Email sent to %s for %s", tech_email, wo_code)
                    else:
                        logger.warning("SMTP send failed for %s: %s", wo_code, result.error)
            except Exception as exc:
                logger.warning("Email notification failed for %s: %s", wo_code, exc)

    async def _escalate(
        self,
        notification_id: str,
        recipient_telegram_id: str,
        title: str,
        message: str,
        reference_id: str | None,
    ) -> None:
        """Send escalation message to FM and secondary contacts."""
        from app.config.settings import settings
        from app.services.telegram_message_sender import get_telegram_sender

        sender = get_telegram_sender()

        escalation_msg = (
            f"⚠️ *ESCALATION*\n"
            f"No acknowledgement received for:\n"
            f"*{title}*\n"
            f"{message[:200]}\n"
            f"Reference: {reference_id or 'N/A'}"
        )

        # Send to original recipient
        await sender.send_text(chat_id=recipient_telegram_id, text=escalation_msg)

        # Also notify secondary FM chat from settings
        secondary = getattr(settings, "sentry_fm_chat_id", None)
        if secondary and secondary != recipient_telegram_id:
            await sender.send_text(chat_id=secondary, text=f"[ESCALATION COPY]\n{escalation_msg}")

        # Update escalated flag
        try:
            await self.notification_repo.update_delivery_log_escalated(
                notification_id=notification_id,
                escalated_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.warning(f"[CERTIFIED] Failed to mark escalated: {e}")


# Singleton instance for module-level imports
notification_service = NotificationService()
