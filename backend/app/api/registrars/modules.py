"""Module API router registrar.

Registers routers for bolt-on modules: security, fire, HVAC, sustainability,
contracts, pricing, and commercial analytics.
"""

from fastapi import FastAPI

from app.api import (
    complaints,
    contracts,
    equipment_lookup,
    fire,
    health_config,
    modules,
    municipal_billing,
    pricing,
    security,
    sustainability,
)


def register_modules_routers(app: FastAPI) -> None:
    """Register bolt-on module API routers."""
    # Module registry
    app.include_router(modules.router, prefix="/api", tags=["modules"])

    # Security and fire safety modules
    app.include_router(security.router, tags=["security"])
    app.include_router(fire.router, tags=["fire"])

    # Health configuration
    app.include_router(health_config.router, tags=["health-config"])

    # Sustainability & ESG
    app.include_router(sustainability.router, prefix="/api", tags=["sustainability"])

    # Contract management and pricing
    app.include_router(contracts.router, prefix="/api", tags=["contracts"])
    app.include_router(pricing.router, prefix="/api", tags=["pricing"])
    app.include_router(municipal_billing.router)

    # Comfort and preferences
    app.include_router(complaints.router, tags=["comfort-complaints"])

    # Equipment lookup
    app.include_router(equipment_lookup.router, prefix="/api", tags=["equipment-lookup"])
