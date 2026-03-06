"""
Operations API router registrar.

Registers routers for work orders, maintenance, inspection, and workflow operations.
"""

from fastapi import FastAPI

from app.api import work_orders, inspection, service_feedback, checklists, inspection_recommendations
from app.api import workflow, baselines, condition
from app.api import remote_ops, remote_commands, dispatch
from app.api import alerts, stats, audit, safety, autonomous, simulation
from app.api import complaints, sentry_webhooks, whatsapp_webhooks, lifecycle_simulation, simulation_analytics
from app.api import integration, concept
from app.api import modules, health_config, service_records, preferences
from app.api import solar, water, sustainability, contracts, pricing, municipal_billing
from app.api import parts_orders, approval_workflow, delivery_tracking, approvals, parasite_decisions
from app.api import security, compliance, notifications, consent
from app.api import privacy
from app.api import asset_health
from app.api import health_rating
from app.api import cafm_integration
from app.api import capex
from app.api import sentry_email
from app.api import security_health
from app.api import servicenow
from app.api import event_bus_monitor
from app.api import n8n
from app.api import notification_router
from app.api import event_intelligence
from app.api import control_policy
from app.api import decision_memory
from app.api import block_bookings


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

    # Simulation and testing
    app.include_router(simulation.router, prefix="/api", tags=["simulation"])
    app.include_router(lifecycle_simulation.router, tags=["lifecycle-simulation"])
    app.include_router(simulation_analytics.router, tags=["simulation-analytics"])

    # Integrations
    app.include_router(integration.router)
    app.include_router(concept.router, tags=["concept-cafm"])
    app.include_router(sentry_webhooks.router, tags=["sentry"])
    app.include_router(whatsapp_webhooks.router, tags=["whatsapp"])

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

    # PARASITE decisions visibility (Phase 80-05)
    app.include_router(parasite_decisions.router)

    # Commercial operations
    app.include_router(contracts.router, prefix="/api", tags=["contracts"])
    app.include_router(pricing.router, prefix="/api", tags=["pricing"])
    app.include_router(municipal_billing.router)

    # Sustainability and utilities
    app.include_router(solar.router, prefix="/api", tags=["solar"])
    app.include_router(water.router, prefix="/api", tags=["water"])
    app.include_router(sustainability.router, prefix="/api", tags=["sustainability"])

    # Security module (Phase 27)
    app.include_router(security.router, tags=["security"])

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

    # Operational Event Intelligence (Phase 145)
    app.include_router(event_intelligence.router, tags=["event-intelligence"])

    # Control Policy Engine (Phase 145)
    app.include_router(control_policy.router, tags=["control-policy"])

    # Decision Memory (Phase 145)
    app.include_router(decision_memory.router, tags=["decision-memory"])

    # Block Booking Detection (Space Intelligence)
    app.include_router(block_bookings.router, tags=["block-bookings"])
