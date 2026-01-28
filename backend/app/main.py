"""BMS Intelligence Backend - FastAPI Application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.api import health, sites, equipment, sensors, alerts, stats, chat, energy, predictions, optimization, devices, audit, safety, autonomous
from app.api import settings as settings_api
from app.middleware.audit_middleware import AuditMiddleware
from app.services.background_scheduler import scheduler_service

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Building Management System Intelligence Platform",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add audit middleware
app.add_middleware(AuditMiddleware)

# Include routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(sites.router, prefix="/api", tags=["sites"])
app.include_router(equipment.router, prefix="/api", tags=["equipment"])
app.include_router(sensors.router, prefix="/api", tags=["sensors"])
app.include_router(alerts.router, prefix="/api", tags=["alerts"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(energy.router, prefix="/api", tags=["energy"])
app.include_router(predictions.router, prefix="/api", tags=["predictions"])
app.include_router(optimization.router, prefix="/api", tags=["optimization"])
app.include_router(devices.router, prefix="/api", tags=["devices"])
app.include_router(safety.router, tags=["safety"])
app.include_router(autonomous.router, tags=["autonomous"])
app.include_router(audit.router, tags=["audit"])
app.include_router(settings_api.router, prefix="/api", tags=["settings"])


@app.on_event("startup")
async def startup_event():
    """Initialize background services on startup."""
    # Start background scheduler for demo data generation
    scheduler_service.start()

    # Generate initial demo data and schedule periodic updates (60 seconds)
    scheduler_service.add_demo_data_job(interval_seconds=60)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup background services on shutdown."""
    scheduler_service.stop()


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "BMS Intelligence API", "version": settings.app_version}
