"""Safety and simulation API router registrar.

Registers routers for safety systems, autonomous decision making,
and BMS simulation.
"""

from fastapi import FastAPI

from app.api import safety, autonomous, simulation, audit, service_records, sentry_webhooks, ocr


def register_safety_simulation_routers(app: FastAPI) -> None:
    """Register safety and simulation API routers."""
    # Safety systems
    app.include_router(safety.router, tags=["safety"])

    # Autonomous decision making
    app.include_router(autonomous.router, tags=["autonomous"])

    # Audit logging
    app.include_router(audit.router, tags=["audit"])

    # BMS simulation
    app.include_router(simulation.router, prefix="/api", tags=["simulation"])

    # Service records and ML data collection
    app.include_router(service_records.router, tags=["service-records"])

    # Sentry integration
    app.include_router(sentry_webhooks.router, tags=["sentry"])

    # OCR for service sheets
    app.include_router(ocr.router, prefix="/api", tags=["ocr"])
