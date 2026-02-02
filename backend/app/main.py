"""BMS Intelligence Backend - FastAPI Application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.api import health, sites, equipment, sensors, alerts, stats, chat, energy, predictions, optimization, devices, audit, safety, autonomous, simulation
from app.api import settings as settings_api  # JSON-based (deprecated)
from app.api import settings_db  # Supabase-based (new)
from app.api import hybrid_chat  # Hybrid AI (Ollama + Claude)
from app.api import equipment_lookup  # Fault code & parts lookup
from app.api import diagnosis  # Guided diagnosis flows
from app.api import vision  # AI vision for equipment photos
from app.api import preferences  # Dashboard preferences
from app.api import integration  # BMS/CAFM integration
from app.api import concept  # Concept Evolution CAFM data
from app.api import dali  # DALI-2 lighting integration
from app.api import complaints  # Comfort complaint handling
from app.api import mcp  # MCP (Model Context Protocol) server
from app.api import mcp_sse  # MCP SSE transport for remote clients
from app.api import mcp_openai  # MCP OpenAI ChatGPT connector
from app.api import buildings  # Building management (onboarding)
from app.api import generators  # Generator/SCADA integration
from app.api import energy_centre  # Energy centre (MV/LV, ATS, meters, UPS)
from app.api import modules  # Module registry (bolt-on modules)
from app.api import hvac  # HVAC module API
from app.api import health_config  # Health calculation config API
from app.api import service_records  # Phase 41 ML service records
from app.api import clawd_webhooks  # Phase 41 Clawd integration
from app.api import ocr  # Phase 41-02 OCR for service sheets
from app.api import ml_predictions  # Phase 43 ML predictions & anomaly detection
from app.api import timeseries  # Phase 42 InfluxDB time-series data
from app.api import sensor_analysis  # Phase 41-03 phyphox sensor analysis
from app.api import features  # Phase 42-02 ML feature store
from app.api import data_quality  # Phase 42-03 Data quality monitoring
from app.api import survival  # Phase 43-03 Survival analysis (Cox PH)
from app.api import classification  # Phase 43-04 Failure type classification (Random Forest)
from app.api import rag  # Phase 44 RAG (Retrieval-Augmented Generation)
# from app.api import baseline  # Phase 44 Asset Baseline Assessment - TODO: Fix import errors
# from app.api import inspection  # Phase 45 Routine Inspection & Maintenance - TODO: Fix import errors
from app.middleware.audit_middleware import AuditMiddleware
from app.services.background_scheduler import scheduler_service
from app.api.simulation import simulation_service  # BMS simulation service
from app.services.health_simulation_service import health_simulation_service  # Supabase health simulation

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
app.include_router(settings_api.router, prefix="/api", tags=["settings"])  # JSON-based (deprecated)
app.include_router(settings_db.router, prefix="/api/db", tags=["settings-db"])  # Supabase-based
app.include_router(hybrid_chat.router, tags=["hybrid-chat"])  # Hybrid AI (Ollama + Claude)
app.include_router(equipment_lookup.router, prefix="/api", tags=["equipment-lookup"])  # Fault code & parts
app.include_router(diagnosis.router, prefix="/api", tags=["diagnosis"])  # Guided diagnosis flows
app.include_router(vision.router, prefix="/api", tags=["vision"])  # AI vision for equipment photos
app.include_router(preferences.router, prefix="/api", tags=["preferences"])  # Dashboard preferences
app.include_router(integration.router)  # BMS/CAFM integration
app.include_router(concept.router, tags=["concept-cafm"])  # Concept Evolution CAFM data
app.include_router(simulation.router, prefix="/api", tags=["simulation"])  # BMS simulation
app.include_router(dali.router, tags=["dali-lighting"])  # DALI-2 lighting integration
app.include_router(complaints.router, tags=["comfort-complaints"])  # Comfort complaint handling
app.include_router(mcp.router, tags=["mcp"])  # MCP (Model Context Protocol) for AI tool integration
app.include_router(mcp_sse.router, tags=["mcp-sse"])  # MCP SSE transport for remote clients
app.include_router(mcp_openai.router, tags=["mcp-openai"])  # MCP OpenAI ChatGPT connector
app.include_router(buildings.router, tags=["buildings"])  # Building management (onboarding)
app.include_router(generators.router, prefix="/api", tags=["generators"])  # Generator/SCADA
app.include_router(energy_centre.router, prefix="/api", tags=["energy-centre"])  # Energy centre
app.include_router(modules.router, prefix="/api", tags=["modules"])  # Module registry (bolt-on)
app.include_router(hvac.router, prefix="/api", tags=["hvac"])  # HVAC module
app.include_router(health_config.router, tags=["health-config"])  # Health config
app.include_router(service_records.router, tags=["service-records"])  # Phase 41 ML data collection
app.include_router(clawd_webhooks.router, tags=["clawd"])  # Phase 41 Clawd integration
app.include_router(ocr.router, prefix="/api", tags=["ocr"])  # Phase 41-02 OCR
app.include_router(ml_predictions.router)  # Phase 43 ML predictions & anomaly detection
app.include_router(timeseries.router)  # Phase 42 InfluxDB time-series data
app.include_router(sensor_analysis.router)  # Phase 41-03 phyphox sensor analysis
app.include_router(features.router)  # Phase 42-02 ML feature store
app.include_router(data_quality.router)  # Phase 42-03 Data quality monitoring
app.include_router(survival.router)  # Phase 43-03 Survival analysis
app.include_router(classification.router, prefix="/api/classification", tags=["classification"])  # Phase 43-04 Failure type classification
app.include_router(rag.router, tags=["rag"])  # Phase 44 RAG with pgvector
# app.include_router(baseline.router)  # Phase 44 Asset Baseline Assessment - TODO: Fix import errors
# app.include_router(inspection.router)  # Phase 45 Routine Inspection & Maintenance - TODO: Fix import errors


@app.on_event("startup")
async def startup_event():
    """Initialize background services on startup."""
    # Start background scheduler for demo data generation
    scheduler_service.start()

    # Generate initial demo data and schedule periodic updates (60 seconds)
    scheduler_service.add_demo_data_job(interval_seconds=60)

    # Start AI optimization analysis job (runs every 15 minutes)
    # Scans all sites with optimization_enabled=true and generates recommendations
    # When a recommendation is generated, the flashing lightbulb appears on dashboard
    scheduler_service.add_optimization_analysis_job(interval_seconds=900)  # 15 minutes

    # Start prediction generation job (runs every 5 minutes)
    # Scans equipment health scores and creates predictions for at-risk equipment
    # When equipment health drops below 90%, a prediction is auto-generated
    scheduler_service.add_prediction_generation_job(interval_seconds=300)  # 5 minutes

    # Start BMS simulation service (in-memory demo)
    try:
        await simulation_service.start_simulation()
        print("BMS Simulation service started successfully")
    except Exception as e:
        print(f"Failed to start simulation service: {e}")

    # Start health simulation service (writes to Supabase, triggers Clawd alerts)
    # Runs every hour between 08:00-17:00
    try:
        await health_simulation_service.start()
        print("Health simulation service started (hourly, 08:00-17:00)")
    except Exception as e:
        print(f"Failed to start health simulation service: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup background services on shutdown."""
    scheduler_service.stop()
    await health_simulation_service.stop()


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "BMS Intelligence API", "version": settings.app_version}
