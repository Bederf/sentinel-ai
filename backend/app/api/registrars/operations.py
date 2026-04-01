"""
Operations API router registrar.

Registers routers for work orders, maintenance, inspection, and workflow operations.
"""

from fastapi import FastAPI

from app.api import (
    ai_usage,
    alert_muting,
    alert_routing,
    alerts,
    approval,
    approval_workflow,
    approvals,
    asset_health,
    audit,
    autonomous,
    baselines,
    block_bookings,
    cafm_integration,
    capex,
    checklists,
    complaints,
    compliance,
    concept,
    concept_rag,
    concierge,
    condition,
    consent,
    contracts,
    control_policy,
    correlation,
    decision_memory,
    decisions,
    delivery_tracking,
    dispatch,
    event_bus_monitor,
    event_intelligence,
    graph_webhook_endpoint,
    health_config,
    health_rating,
    inspection,
    inspection_recommendations,
    integration,
    modules,
    municipal_billing,
    n8n,
    notification_router,
    notifications,
    parasite_decisions,
    parts_orders,
    preferences,
    pricing,
    privacy,
    reception,
    remote_commands,
    remote_ops,
    review_queue,
    safety,
    security_health,
    semantic_classification,
    sentry_email,
    sentry_webhooks,
    service_feedback,
    service_records,
    servicenow,
    signal_replay,
    space,
    stats,
    sustainability,
    trust_scoring,
    water,
    whatsapp_webhooks,
    work_orders,
    workflow,
)
from app.api import technicians as technicians_api
from app.config.settings import settings


def register_operations_routers(app: FastAPI) -> None:
    """Register operations API routers (work orders, maintenance, workflow)."""
    # Work orders and maintenance
    app.include_router(work_orders.router, prefix="/api", tags=["work-orders"])
    app.include_router(inspection.router, tags=["inspection"])
    app.include_router(inspection_recommendations.router, tags=["inspection-recommendations"])
    app.include_router(service_feedback.router, tags=["service-feedback"])
    app.include_router(checklists.router, tags=["checklists"])
    app.include_router(complaints.router, tags=["comfort-complaints"])
    app.include_router(parts_orders.router, tags=["parts-orders"])

    # Workflow orchestration
    app.include_router(workflow.router, tags=["workflow"])
    app.include_router(baselines.router, tags=["baselines"])
    app.include_router(condition.router, tags=["condition"])

    # Remote operations
    app.include_router(remote_ops.router, tags=["remote-ops"])
    app.include_router(remote_commands.router, prefix="/api/remote", tags=["remote-ops"])
    app.include_router(dispatch.router, prefix="/api/dispatch", tags=["dispatch"])

    # Alerts, stats, audit, safety
    app.include_router(alerts.router, prefix="/api", tags=["alerts"])
    app.include_router(stats.router, prefix="/api", tags=["stats"])
    app.include_router(audit.router, tags=["audit"])
    app.include_router(safety.router, tags=["safety"])
    app.include_router(autonomous.router, tags=["autonomous"])

    # Integrations
    app.include_router(integration.router)
    app.include_router(concept.router, tags=["concept-cafm"])
    app.include_router(sentry_webhooks.router, tags=["sentry"])
    app.include_router(whatsapp_webhooks.router, tags=["whatsapp"])
    app.include_router(graph_webhook_endpoint.router, tags=["graph_webhook"])

    # Module registry and configuration
    app.include_router(modules.router, prefix="/api", tags=["modules"])
    app.include_router(health_config.router, tags=["health-config"])
    app.include_router(service_records.router, tags=["service-records"])
    app.include_router(preferences.router, prefix="/api", tags=["preferences"])

    # Multi-channel notifications (Phase 102)
    app.include_router(notifications.router, prefix="/api", tags=["notifications"])

    # POPIA consent management
    app.include_router(consent.router, prefix="/api", tags=["consent"])
    app.include_router(privacy.router, tags=["privacy"])

    # Parts ordering and approval workflow (Phase 20)
    app.include_router(approval_workflow.router, tags=["approval-workflow"])
    app.include_router(delivery_tracking.router, tags=["delivery-tracking"])

    # Niagara equipment control approvals (Phase 68-02)
    app.include_router(approvals.router, tags=["approvals"])

    # Phase 170: Control actuation loop — supervised execution
    app.include_router(approval.router, tags=["approval-execute"])

    # PARASITE decisions visibility (Phase 80-05)
    app.include_router(parasite_decisions.router)

    # Commercial operations
    app.include_router(contracts.router, prefix="/api", tags=["contracts"])
    app.include_router(pricing.router, prefix="/api", tags=["pricing"])
    app.include_router(municipal_billing.router)

    # Sustainability and utilities
    app.include_router(water.router, prefix="/api", tags=["water"])
    app.include_router(sustainability.router, prefix="/api", tags=["sustainability"])

    # Security module (Phase 27)
    # Compliance module (Phase 28)
    app.include_router(compliance.router, tags=["compliance"])

    # Asset health + baseline (Phase 109A)
    app.include_router(asset_health.router, tags=["asset-health"])

    # Health rating timeline (Phase 109B)
    app.include_router(health_rating.router, tags=["health-rating"])

    # CAFM integration (Phase 110 — completes v5.0)
    app.include_router(cafm_integration.router, tags=["cafm-integration"])

    # CapEx planning engine (Phase 128)
    app.include_router(capex.router, prefix="/api", tags=["capex"])

    # Email intake pipeline (Phase 131)
    app.include_router(sentry_email.router, tags=["sentry-email"])

    # Security health check (Phase 137-09)
    app.include_router(security_health.router, tags=["security-health"])

    # ServiceNow ITSM integration (Phase 138)
    app.include_router(servicenow.router, tags=["servicenow"])

    # Event bus monitoring (Phase 139)
    app.include_router(event_bus_monitor.router, tags=["event-bus"])

    # n8n workflow automation (Phase 140)
    app.include_router(n8n.router, tags=["n8n"])

    # Sentry notification router — importance-based delivery (Phase 140)
    app.include_router(notification_router.router, tags=["notification-router"])

    # Alert routing rules + equipment muting (Phase 159)
    app.include_router(alert_routing.router, tags=["alert-routing"])
    app.include_router(alert_muting.router, tags=["alert-muting"])

    # AI Usage & Cost Tracking
    app.include_router(ai_usage.router, tags=["ai-usage"])

    # Technician Registry (handoff blocker)
    app.include_router(technicians_api.router, tags=["technicians"])

    # Operational Event Intelligence (Phase 145)
    app.include_router(event_intelligence.router, tags=["event-intelligence"])

    # Control Policy Engine (Phase 145)
    app.include_router(control_policy.router, tags=["control-policy"])

    # Decision Memory (Phase 145)
    app.include_router(decision_memory.router, tags=["decision-memory"])

    # Block Booking Detection (Space Intelligence)
    app.include_router(block_bookings.router, tags=["block-bookings"])

    # Ghost Booking & Right-Sizing Detection (Space Intelligence Rev 1.2)
    app.include_router(space.router, tags=["space-intelligence"])

    # Correlation & Issue Intelligence (Phase 155)
    app.include_router(correlation.router, tags=["correlation"])

    # Concierge Intelligence Dashboard (Phase 161)
    app.include_router(concierge.router, tags=["concierge"])

    # Semantic Classification (Phase 162)
    app.include_router(semantic_classification.router, tags=["semantic-classification"])

    # Dynamic Validation + Trust Scoring (Phase 162-04)
    app.include_router(trust_scoring.router, tags=["trust-scoring"])

    # Review Queue — Human-in-the-loop for Classification (Phase 162-05)
    app.include_router(review_queue.router, tags=["review-queue"])

    # Signal Replay Tool (Phase 159-04)
    app.include_router(signal_replay.router, tags=["signal-replay"])

    # Fuel Monitoring (Phase 150)
    if settings.fuel_monitoring_enabled:
        from app.api.fuel import router as fuel_router

        app.include_router(fuel_router, tags=["fuel"])

    # Plant Room Alerts — Desigo email->WhatsApp pipeline (Phase 146)
    if settings.plant_alerts_enabled:
        from app.plant.plant_alerts import router as plant_alerts_router

        app.include_router(plant_alerts_router, tags=["plant-alerts"])

    app.include_router(concept_rag.router)

    # Visitor Management — Reception API (Phase 176)
    app.include_router(reception.router, prefix="/api", tags=["reception"])

    # Decision Moment API — Crisis State page (Phase 164)
    app.include_router(decisions.router, tags=["decisions"])
