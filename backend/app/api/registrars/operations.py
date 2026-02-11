"""
Operations API router registrar.

Registers routers for work orders, maintenance, inspection, and workflow operations.
"""

from fastapi import FastAPI

from app.api import work_orders, inspection, service_feedback, checklists
from app.api import workflow, baselines, condition
from app.api import remote_ops, remote_commands, dispatch
from app.api import alerts, stats, audit, safety, autonomous, simulation
from app.api import complaints, clawd_webhooks, lifecycle_simulation, simulation_analytics
from app.api import integration, concept
from app.api import modules, health_config, service_records, preferences
from app.api import solar, water, sustainability, contracts, pricing, municipal_billing
from app.api import parts_orders, approval_workflow, delivery_tracking


def register_operations_routers(app: FastAPI) -> None:
    """Register operations API routers (work orders, maintenance, workflow)."""
    # Work orders and maintenance
    app.include_router(work_orders.router, prefix="/api", tags=["work-orders"])
    app.include_router(inspection.router, tags=["inspection"])
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
    app.include_router(clawd_webhooks.router, tags=["clawd"])

    # Module registry and configuration
    app.include_router(modules.router, prefix="/api", tags=["modules"])
    app.include_router(health_config.router, tags=["health-config"])
    app.include_router(service_records.router, tags=["service-records"])
    app.include_router(preferences.router, prefix="/api", tags=["preferences"])

    # Parts ordering and approval workflow (Phase 20)
    app.include_router(approval_workflow.router, tags=["approval-workflow"])
    app.include_router(delivery_tracking.router, tags=["delivery-tracking"])

    # Commercial operations
    app.include_router(contracts.router, prefix="/api", tags=["contracts"])
    app.include_router(pricing.router, prefix="/api", tags=["pricing"])
    app.include_router(municipal_billing.router)

    # Sustainability and utilities
    app.include_router(solar.router, prefix="/api", tags=["solar"])
    app.include_router(water.router, prefix="/api", tags=["water"])
    app.include_router(sustainability.router, prefix="/api", tags=["sustainability"])
