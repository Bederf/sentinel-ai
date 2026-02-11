"""Module API router registrar.

Registers routers for bolt-on modules: security, fire, HVAC, sustainability,
contracts, pricing, and commercial analytics.
"""

from fastapi import FastAPI

from app.api import security, fire, hvac, modules, health_config
from app.api import sustainability, contracts, pricing, municipal_billing
from app.api import complaints, equipment_lookup


def register_modules_routers(app: FastAPI) -> None:
    """Register bolt-on module API routers."""
    # Module registry
    app.include_router(modules.router, prefix="/api", tags=["modules"])

    # Security and fire safety modules
    app.include_router(security.router, tags=["security"])
    app.include_router(fire.router, tags=["fire"])

    # HVAC module
    app.include_router(hvac.router, prefix="/api", tags=["hvac"])

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
