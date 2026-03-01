"""
SENTINEL Default Event Subscribers — Phase 139-02.

Registers 7 default subscribers on the event bus that wire SENTINEL's existing
components to the pub/sub event stream. All subscribers start as logging stubs
with detailed TODO markers showing exactly where to wire real services.

Subscriber list:
1. audit_log_all_events       — logs every event for compliance
2. route_high_importance_to_sentry — immediate push for HIGH/CRITICAL
3. collect_medium_for_digest  — batches MEDIUM events for daily digest
4. trigger_ai_diagnosis       — AI diagnosis on anomaly detection
5. auto_create_work_order     — creates WO on completed diagnosis
6. watch_for_acknowledgement  — escalation watcher for unacked notifications
7. trigger_n8n_workflow       — n8n workflow trigger on WO creation
"""

import logging

from app.services.event_bus import Importance, SentinelEvent, get_event_bus

logger = logging.getLogger("sentinel.event_subscribers")


def register_default_subscribers() -> None:
    """Register all default event subscribers on the singleton event bus.

    Call once at application startup. Each subscriber is registered via the
    ``@bus.on()`` decorator pattern inside this function so that registration
    only happens when explicitly invoked (not at import time).
    """
    bus = get_event_bus()

    # ------------------------------------------------------------------
    # 1. Audit Logger — logs every event for compliance
    # ------------------------------------------------------------------
    @bus.on("*")
    async def audit_log_all_events(event: SentinelEvent) -> None:
        """Log every event to the audit trail.

        TODO: Wire to audit_service to persist to Supabase ``audit_events`` table.
              Replace logger call with:
                  from app.services.audit_service import audit_service
                  await audit_service.log_event(
                      event_type=event.event_type,
                      source=event.source,
                      payload=event.payload,
                      importance=event.importance.name,
                      site_id=event.site_id,
                      equipment_id=event.equipment_id,
                      correlation_id=event.correlation_id,
                  )
        """
        logger.info(
            "AUDIT | %s | importance=%s | source=%s | site=%s | equip=%s | corr=%s",
            event.event_type,
            event.importance.name,
            event.source,
            event.site_id or "-",
            event.equipment_id or "-",
            event.correlation_id or "-",
        )

    # ------------------------------------------------------------------
    # 2. Sentry Push Router — immediate push for HIGH/CRITICAL events
    # ------------------------------------------------------------------
    @bus.on("*", min_importance=Importance.HIGH)
    async def route_high_importance_to_sentry(event: SentinelEvent) -> None:
        """Push HIGH/CRITICAL events to Sentry bot for immediate notification.

        Creates a chain event ``sentry.notification_sent`` appended directly
        to the bus history (not emitted) to avoid infinite recursion.

        TODO: Wire to Sentry bot WhatsApp/Telegram push:
                  from app.services.sentry_notification_service import sentry_notification_service
                  await sentry_notification_service.push_alert(
                      message=f"[{event.importance.name}] {event.event_type}: {event.payload}",
                      site_id=event.site_id,
                      equipment_id=event.equipment_id,
                      priority="urgent" if event.importance >= Importance.CRITICAL else "high",
                  )
        """
        logger.warning(
            "SENTRY PUSH | %s | importance=%s | site=%s | equip=%s",
            event.event_type,
            event.importance.name,
            event.site_id or "-",
            event.equipment_id or "-",
        )

        # Create chain event for escalation tracking (append directly to
        # avoid recursion — do NOT call bus.emit() here).
        chain_event = event.chain(
            event_type="sentry.notification_sent",
            source="event_subscribers.route_high_importance_to_sentry",
            payload={
                "original_event_type": event.event_type,
                "original_importance": event.importance.name,
                "channel": "logging_stub",  # TODO: change to "telegram" / "whatsapp"
                "acknowledged": False,
            },
        )
        # Append directly to history for the escalation watcher to see
        bus._history.append(chain_event)

    # ------------------------------------------------------------------
    # 3. Sentry Digest Collector — batches MEDIUM events for daily digest
    # ------------------------------------------------------------------
    @bus.on("*", min_importance=Importance.MEDIUM)
    async def collect_medium_for_digest(event: SentinelEvent) -> None:
        """Collect MEDIUM-importance events for the daily digest.

        Only collects MEDIUM events. HIGH and CRITICAL are handled by the
        push router (subscriber 2) and should NOT appear in the digest.

        TODO: Wire to digest service:
                  from app.services.digest_service import digest_service
                  if event.importance == Importance.MEDIUM:
                      await digest_service.add_to_digest(
                          event_type=event.event_type,
                          summary=str(event.payload),
                          site_id=event.site_id,
                          equipment_id=event.equipment_id,
                          timestamp=event.timestamp,
                      )
        """
        # Only collect MEDIUM — HIGH/CRITICAL are pushed immediately
        if event.importance != Importance.MEDIUM:
            return

        logger.info(
            "DIGEST COLLECT | %s | site=%s | equip=%s",
            event.event_type,
            event.site_id or "-",
            event.equipment_id or "-",
        )

    # ------------------------------------------------------------------
    # 4. AI Diagnosis Trigger — triggers AI diagnosis on anomaly detection
    # ------------------------------------------------------------------
    @bus.on("sensor.anomaly_detected")
    async def trigger_ai_diagnosis(event: SentinelEvent) -> None:
        """Trigger AI diagnosis when a sensor anomaly is detected.

        TODO: Wire to AI service:
                  from app.services.ai_optimizer import ai_optimizer
                  diagnosis = await ai_optimizer.diagnose_anomaly(
                      equipment_id=event.equipment_id,
                      anomaly_data=event.payload,
                      site_id=event.site_id,
                  )
                  # Emit diagnosis result as chain event
                  await bus.emit(event.chain(
                      event_type="ai.diagnosis_complete",
                      source="ai_optimizer",
                      payload={"diagnosis": diagnosis, "action_required": diagnosis.get("action_required", False)},
                      importance=Importance.HIGH if diagnosis.get("action_required") else Importance.MEDIUM,
                  ))
        """
        logger.info(
            "AI DIAGNOSIS TRIGGER | anomaly on %s | site=%s | payload_keys=%s",
            event.equipment_id or "-",
            event.site_id or "-",
            list(event.payload.keys()),
        )

    # ------------------------------------------------------------------
    # 5. Auto Work Order — creates WO when diagnosis requires action
    # ------------------------------------------------------------------
    @bus.on("ai.diagnosis_complete")
    async def auto_create_work_order(event: SentinelEvent) -> None:
        """Auto-create a work order when AI diagnosis indicates action is required.

        Only creates WO when:
        - payload["action_required"] is True
        - event importance >= HIGH

        TODO: Wire to work order service:
                  from app.services.work_order_service import work_order_service
                  if event.payload.get("action_required") and event.importance >= Importance.HIGH:
                      wo = await work_order_service.create(
                          title=f"AI Diagnosis: {event.payload.get('diagnosis', {}).get('fault_type', 'Unknown')}",
                          equipment_id=event.equipment_id,
                          site_id=event.site_id,
                          priority="urgent" if event.importance >= Importance.CRITICAL else "high",
                          description=str(event.payload.get("diagnosis", {})),
                          source="ai_auto_diagnosis",
                          correlation_id=event.correlation_id,
                      )
                      # Emit chain event
                      await bus.emit(event.chain(
                          event_type="maintenance.work_order_created",
                          source="event_subscribers.auto_create_work_order",
                          payload={"work_order_id": wo.id, "auto_created": True},
                          importance=event.importance,
                      ))
        """
        action_required = event.payload.get("action_required", False)
        if not action_required or event.importance < Importance.HIGH:
            logger.debug(
                "AUTO WO SKIP | %s | action_required=%s importance=%s",
                event.equipment_id or "-",
                action_required,
                event.importance.name,
            )
            return

        logger.info(
            "AUTO WO CREATE | diagnosis requires action | equip=%s | site=%s | importance=%s",
            event.equipment_id or "-",
            event.site_id or "-",
            event.importance.name,
        )

    # ------------------------------------------------------------------
    # 6. Escalation Watcher — watches for acknowledgement of notifications
    # ------------------------------------------------------------------
    @bus.on("sentry.notification_sent")
    async def watch_for_acknowledgement(event: SentinelEvent) -> None:
        """Watch for unacknowledged HIGH/CRITICAL notifications and escalate.

        Monitors ``sentry.notification_sent`` events. If not acknowledged
        within the escalation window, escalates to the next tier.

        TODO: Wire to escalation service:
                  from app.services.escalation_engine import escalation_engine
                  await escalation_engine.start_watching(
                      notification_id=event.event_id,
                      original_event_type=event.payload.get("original_event_type"),
                      importance=event.payload.get("original_importance"),
                      site_id=event.site_id,
                      equipment_id=event.equipment_id,
                      escalation_window_minutes=15,  # escalate if no ack in 15 min
                  )
        """
        logger.info(
            "ESCALATION WATCH | notification=%s | original=%s | importance=%s | acked=%s",
            event.event_id,
            event.payload.get("original_event_type", "?"),
            event.payload.get("original_importance", "?"),
            event.payload.get("acknowledged", False),
        )

    # ------------------------------------------------------------------
    # 7. n8n Workflow Trigger — triggers n8n on work order creation
    # ------------------------------------------------------------------
    @bus.on("maintenance.work_order_created")
    async def trigger_n8n_workflow(event: SentinelEvent) -> None:
        """Trigger n8n workflow for contractor dispatch on WO creation.

        Wired to n8n service (Phase 140). Additional n8n event subscribers
        (escalation, system alerts) registered separately via
        n8n_event_subscriber.register_n8n_subscribers().
        """
        from app.services.n8n_service import get_n8n_service

        service = get_n8n_service()
        if not service.is_configured:
            logger.debug("n8n not configured — logging WO event only")
            logger.info(
                "N8N TRIGGER | work_order=%s | site=%s | equip=%s | auto=%s",
                event.payload.get("work_order_id", "?"),
                event.site_id or "-",
                event.equipment_id or "-",
                event.payload.get("auto_created", False),
            )
            return

        result = await service.trigger_webhook(
            webhook_path="work-order-created",
            payload={
                "work_order_id": event.payload.get("work_order_id"),
                "site_id": event.site_id,
                "equipment_id": event.equipment_id,
                "priority": "urgent" if event.importance >= Importance.CRITICAL else "normal",
                "auto_created": event.payload.get("auto_created", False),
            },
        )
        if result.get("success"):
            logger.info(
                "N8N TRIGGER | work_order=%s dispatched via webhook",
                event.payload.get("work_order_id", "?"),
            )
        else:
            logger.warning(
                "N8N TRIGGER | work_order=%s failed: %s",
                event.payload.get("work_order_id", "?"),
                result.get("reason", "unknown"),
            )

    # ------------------------------------------------------------------
    # Registration complete
    # ------------------------------------------------------------------
    sub_count = len(bus.get_subscriptions())
    logger.info("Registered %d default event subscribers", sub_count)
