"""
Core API router registrar.

Registers core API routers for authentication, settings, sites, and health.
"""

from fastapi import FastAPI

from app.api import (
    auth,
    cache,
    events,
    governance_metrics_api,
    health,
    login_audit,
    mfa,
    settings_db,
    sites,
    sites_aggregation,
    space_settings,
    system_health,
    user_access,
    user_entitlements,
)
from app.api import metrics as prometheus_metrics
from app.api import settings as settings_api


def register_core_routers(app: FastAPI) -> None:
    """Register core API routers (auth, settings, sites, cache, health)."""
    # Health and monitoring
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(system_health.router, tags=["system-health"])
    app.include_router(cache.router, tags=["cache"])
    app.include_router(events.router, tags=["events"])

    # Prometheus metrics (no prefix — mounted at root /metrics)
    app.include_router(prometheus_metrics.router, tags=["monitoring"])

    # Sites (core entity) - IMPORTANT: sites_aggregation MUST be first for specific routes to match
    app.include_router(sites_aggregation.router, prefix="/api", tags=["sites-aggregation"])
    app.include_router(sites.router, prefix="/api", tags=["sites"])

    # Settings (JSON-based deprecated + Supabase-based new)
    app.include_router(settings_api.router, prefix="/api", tags=["settings"])
    app.include_router(settings_db.router, prefix="/api/db", tags=["settings-db"])

    # Space optimization settings (grace periods, concierge CRUD)
    app.include_router(space_settings.router, prefix="/api", tags=["space-settings"])

    # Governance metrics
    app.include_router(governance_metrics_api.router, tags=["governance"])

    # Authentication and authorization
    app.include_router(auth.router, tags=["auth"])
    app.include_router(user_access.router, tags=["user-access"])
    app.include_router(user_access.self_service_router, tags=["user-access"])
    app.include_router(login_audit.router, tags=["login-audit"])
    app.include_router(mfa.router, tags=["mfa"])
    app.include_router(user_entitlements.router, prefix="/api", tags=["user-entitlements"])
