"""Router registration for FastAPI application.

This module consolidates all router registration into a single function,
extracted from main.py to improve maintainability and organization.
"""

from fastapi import FastAPI

from app.api.registrars.core import register_core_routers
from app.api.registrars.building import register_building_routers
from app.api.registrars.operations import register_operations_routers
from app.api.registrars.analytics import register_analytics_routers


def register_all_routes(app: FastAPI) -> None:
    """Register all API routers by domain.

    This function registers all API routers using the domain-based
    registrar modules created in Phase 67-01. This reduces main.py
    from 83 individual include_router() calls to 4 registrar calls.

    Domain organization:
    - Core: auth, settings, sites, cache, health (9 routers)
    - Building: buildings, equipment, devices, HVAC, lighting, fire, security, energy centre, Niagara (17 routers)
    - Operations: work orders, maintenance, inspection, workflow, remote ops, integrations, commercial (23 routers)
    - Analytics: chat/ai, predictions, optimization, ML, time series, MCP (21 routers)

    Args:
        app: The FastAPI application instance
    """
    # Register core API routers (auth, settings, sites, cache, health)
    register_core_routers(app)

    # Register building management routers (equipment, devices, HVAC, lighting, etc.)
    register_building_routers(app)

    # Register operations routers (work orders, maintenance, inspection, workflow, etc.)
    register_operations_routers(app)

    # Register analytics routers (chat/ai, predictions, optimization, ML, etc.)
    register_analytics_routers(app)
