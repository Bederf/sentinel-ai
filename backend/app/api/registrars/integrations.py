"""Integration API router registrar.

Registers routers for third-party integrations: Niagara, BACnet,
lighting, SIMBIOT Concept, and energy systems.
"""

from fastapi import FastAPI

from app.api import (
    concept,
    energy,
    energy_centre,
    generators,
    integration,
    lighting,
    niagara,
    niagara_bacnet,
    niagara_discovery,
    simbiot,
    solar,
    water,
)


def register_integrations_routers(app: FastAPI) -> None:
    """Register integration API routers."""
    # Niagara integration
    app.include_router(niagara.router, tags=["niagara-obix"])
    app.include_router(niagara_bacnet.router, tags=["niagara-bacnet"])
    app.include_router(niagara_discovery.router, tags=["niagara-discovery"])

    # Lighting integration
    app.include_router(lighting.router, tags=["lighting"])

    # Energy systems
    app.include_router(energy.router, prefix="/api", tags=["energy"])
    app.include_router(generators.router, prefix="/api", tags=["generators"])
    app.include_router(energy_centre.router, prefix="/api", tags=["energy-centre"])

    # Solar PV & BESS
    app.include_router(solar.router, prefix="/api", tags=["solar"])

    # Water meter integration
    app.include_router(water.router, prefix="/api", tags=["water"])

    # SIMBIOT site & adapter configuration (Phase 206)
    app.include_router(simbiot.router, tags=["simbiot"])

    # BMS/CAFM integrations
    app.include_router(integration.router)
    app.include_router(concept.router, tags=["concept-cafm"])
