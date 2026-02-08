"""BMS Intelligence Backend - FastAPI Application."""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config.settings import settings
from app.middleware.auth_middleware import _authenticate_request, _extract_ip_address
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
from app.api import workflow  # Phase 53 Workflow orchestration & triggers
from app.api import baselines  # Phase 54-01 Equipment Baseline Assessment
from app.api import condition  # Phase 56-01 Condition trending & degradation analysis
from app.api import ml_feedback  # Phase 57-02 ML feedback loop
from app.api import repair_effectiveness  # Phase 57-01 Repair effectiveness validation
from app.api import remote_ops  # Phase 59-01 Remote operations monitoring
from app.api import remote_commands  # Phase 59-02 Remote command execution
from app.api import dispatch  # Phase 59-03 Smart dispatch & task bundling
from app.api import niagara  # Phase 60-02 Niagara oBIX integration
from app.api import niagara_bacnet  # Phase 60-01 Niagara BACnet/IP integration
from app.api import niagara_discovery  # Phase 60-03 Niagara point discovery
from app.api import fire  # Phase 61-01 Fire & Life Safety
from app.api import security  # Phase 58-01 Security Module (access control, CCTV, occupancy)
from app.api import work_orders  # Work orders (Clawd bot integration)
from app.api import inspection  # Phase 55 Routine Inspection & Maintenance
from app.api import auth  # Authentication endpoints
from app.api import user_access  # User site access management
from app.api import login_audit  # Login audit logs
from app.api import mfa  # Phase 58.1 MFA for privileged access (FSR 4.6)
from app.api import equipment_metadata  # Equipment notes and metadata
from app.api import dali_discovery  # DALI device discovery
from app.api import equipment_discovery  # Unified equipment discovery (DALI, BACnet, Modbus)
from app.api import service_feedback  # Phase 59 Service feedback & health score integration
from app.api import lifecycle_simulation  # 24-hour building lifecycle simulation
from app.api import cache  # Redis cache management
from app.api import simulation_analytics  # Simulation analytics pipeline
from app.api import local_chat  # Phase 44-03 Local LLM conversational interface
from app.api import ml_retraining  # Phase 45-01 Online Learning & Automated Retraining
from app.api import fleet_learning  # Phase 45-02 Fleet Learning & Cross-Site Insights
from app.api import mlops  # Phase 45-03 MLOps Monitoring & Success Metrics
from app.api import sustainability  # Phase 29 Sustainability & ESG module
from app.api import solar  # Phase 34 Solar PV & BESS ingestion
from app.api import water  # Phase 35 Water Meter Integration & Leak Detection
from app.api import contracts  # Phase 48 Contract Management
from app.api import pricing  # Phase 52-01 Risk-Based Pricing Tools
from app.api import municipal_billing  # Phase 49 Municipal Billing
from app.middleware.audit_middleware import AuditMiddleware
from app.middleware.security_logging import SecurityLoggingMiddleware
from app.services.background_scheduler import scheduler_service
from app.services.health_simulation_service import health_simulation_service  # Supabase health simulation
from app.services.simbiot_service import simbiot_service  # SIMBIOT Concept Evolution connector

_logger = logging.getLogger("sentinel.security")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Building Management System Intelligence Platform",
)

# =============================================================================
# Rate Limiting (Phase 58-03 H-1)
# =============================================================================
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Return 429 with Retry-After header when rate limit exceeded."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
        headers={"Retry-After": str(exc.retry_after)},
    )


# =============================================================================
# Generic Error Handler (Phase 58-04 M-8)
# Hide internal stack traces in non-debug / production mode.
# =============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler that hides internals in production."""
    if settings.debug:
        # In debug mode, return full detail for developer convenience
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc)},
        )
    # Log the real error server-side, return a generic message to the client
    _logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# =============================================================================
# CORS (Phase 58-03 H-2) — restricted to configured origins
# =============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# =============================================================================
# Security Headers (Phase 58-03 H-6, H-7)
# =============================================================================
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add standard security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not settings.debug:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# =============================================================================
# Global Authentication Enforcement (Phase 58-03 C-1)
# =============================================================================
# Paths that do not require authentication
_PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/login/mfa-complete",
    "/api/auth/register",
    "/api/auth/mfa/verify",
    "/api/auth/verify",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/health",
    "/api/health",
}
_PUBLIC_PREFIXES = (
    "/api/clawd-webhooks",  # Telegram bot callbacks (authenticated via webhook secret)
    "/api/mcp-sse",  # MCP SSE transport (authenticated at MCP layer)
)
_LOCALHOST_IPS = {"127.0.0.1", "::1", "localhost", "testclient"}


@app.middleware("http")
async def enforce_authentication(request: Request, call_next):
    """Global auth enforcement -- all /api/ routes require auth unless whitelisted."""
    path = request.url.path

    # Skip non-API routes and public paths
    if (
        path in _PUBLIC_PATHS
        or path.startswith(_PUBLIC_PREFIXES)
        or not path.startswith("/api/")
    ):
        return await call_next(request)

    # In demo mode, allow localhost without credentials
    if settings.demo_mode:
        source_ip = _extract_ip_address(request)
        # Also treat unknown/missing client as local (e.g. test clients)
        if source_ip in _LOCALHOST_IPS or source_ip == "unknown":
            # Try real auth first; fall back to demo context
            auth_ctx = await _authenticate_request(request)
            request.state.auth = auth_ctx  # may be None (endpoints handle via Depends)
            return await call_next(request)
        # Non-localhost in demo mode: require real auth
        auth_ctx = await _authenticate_request(request)
        if auth_ctx is None:
            return JSONResponse(
                status_code=403,
                content={"detail": "Demo mode is only available from localhost"},
            )
        request.state.auth = auth_ctx
        return await call_next(request)

    # Production / non-demo: require real authentication
    auth_ctx = await _authenticate_request(request)
    if auth_ctx is None:
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.auth = auth_ctx
    return await call_next(request)


# Add security logging middleware (Phase 63 - FSR compliance)
# SecurityLoggingMiddleware runs first (outermost), captures all security events
app.add_middleware(SecurityLoggingMiddleware)

# Add audit middleware (existing - captures device control actions)
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
app.include_router(mcp_openai.wellknown_router, tags=["mcp-discovery"])  # MCP well-known discovery
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
app.include_router(workflow.router, tags=["workflow"])  # Phase 53 Workflow orchestration & triggers
app.include_router(baselines.router, tags=["baselines"])  # Phase 54-01 Equipment Baseline Assessment
app.include_router(condition.router, tags=["condition"])  # Phase 56-01 Condition trending & degradation
app.include_router(ml_feedback.router, tags=["ml-feedback"])  # Phase 57-02 ML feedback loop
app.include_router(repair_effectiveness.router, tags=["repair-effectiveness"])  # Phase 57-01 Repair effectiveness
app.include_router(remote_ops.router, tags=["remote-ops"])  # Phase 59-01 Remote operations monitoring
app.include_router(remote_commands.router, prefix="/api/remote", tags=["remote-ops"])  # Phase 59-02 Remote command execution
app.include_router(dispatch.router, prefix="/api/dispatch", tags=["dispatch"])  # Phase 59-03 Smart dispatch
app.include_router(niagara.router, tags=["niagara-obix"])  # Phase 60-02 Niagara oBIX integration
app.include_router(niagara_bacnet.router, tags=["niagara-bacnet"])  # Phase 60-01 Niagara BACnet/IP integration
app.include_router(niagara_discovery.router, tags=["niagara-discovery"])  # Phase 60-03 Niagara point discovery
app.include_router(fire.router, tags=["fire"])  # Phase 61-01 Fire & Life Safety
app.include_router(security.router, tags=["security"])  # Phase 58-01 Security Module
app.include_router(work_orders.router, prefix="/api", tags=["work-orders"])  # Work orders
app.include_router(service_feedback.router, tags=["service-feedback"])  # Phase 59 Service feedback & health score
app.include_router(lifecycle_simulation.router, tags=["lifecycle-simulation"])  # 24-hour building lifecycle simulation
app.include_router(simulation_analytics.router, tags=["simulation-analytics"])  # Simulation analytics pipeline
app.include_router(inspection.router, tags=["inspection"])  # Phase 55 Routine Inspection & Maintenance
app.include_router(auth.router)  # Authentication (email-based login)

# Initialize rate limiters for auth router (Phase 65-02)
auth.init_rate_limiter(limiter)
app.include_router(user_access.router)  # User site access management (admin)
app.include_router(login_audit.router)  # Login audit logs (admin)
app.include_router(mfa.router)  # Phase 58.1 MFA for privileged access (FSR 4.6)
app.include_router(equipment_metadata.router, prefix="/api", tags=["equipment-metadata"])  # Equipment notes/metadata
app.include_router(dali_discovery.router, prefix="/api", tags=["dali-discovery"])  # DALI device discovery
app.include_router(equipment_discovery.router, prefix="/api", tags=["equipment-discovery"])  # Unified discovery
app.include_router(cache.router, tags=["cache"])  # Redis cache management
app.include_router(local_chat.router, prefix="/api", tags=["local-chat"])  # Phase 44-03 Local LLM chat
app.include_router(ml_retraining.router, tags=["ml-retraining"])  # Phase 45-01 Online Learning & Retraining
app.include_router(fleet_learning.router, tags=["fleet-learning"])  # Phase 45-02 Fleet Learning & Cross-Site Insights
app.include_router(mlops.router, tags=["mlops"])  # Phase 45-03 MLOps Monitoring & Success Metrics
app.include_router(sustainability.router, prefix="/api", tags=["sustainability"])  # Phase 29 Sustainability & ESG
app.include_router(solar.router, prefix="/api", tags=["solar"])  # Phase 34 Solar PV & BESS
app.include_router(water.router, prefix="/api", tags=["water"])  # Phase 35 Water Meter Integration & Leak Detection
app.include_router(contracts.router, prefix="/api", tags=["contracts"])  # Phase 48 Contract Management
app.include_router(pricing.router, prefix="/api", tags=["pricing"])  # Phase 52-01 Risk-Based Pricing Tools
app.include_router(municipal_billing.router)  # Phase 49 Municipal Billing


@app.on_event("startup")
async def startup_event():
    """Initialize background services on startup."""
    import logging
    _logger = logging.getLogger("sentinel.startup")
    testing_mode = os.getenv("TESTING", "").lower() == "true"

    # === Security startup checks ===

    # Block DEMO_MODE in production
    if settings.environment == "production" and settings.demo_mode:
        raise RuntimeError(
            "DEMO_MODE cannot be enabled in production environment. "
            "Set DEMO_MODE=false or ENVIRONMENT=development."
        )

    # Require JWT secret when not in DEMO_MODE (C-2: Secure JWT signing)
    if not settings.demo_mode and not settings.jwt_secret_key and not settings.supabase_key:
        raise RuntimeError(
            "JWT_SECRET_KEY (or SUPABASE_KEY) must be set when DEMO_MODE is disabled. "
            "Generate a 256-bit secret: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "and set JWT_SECRET_KEY in your .env file."
        )

    # Warn about weak JWT secrets (less than 32 characters)
    _jwt_key = settings.jwt_secret_key or settings.supabase_key
    if _jwt_key and len(_jwt_key) < 32 and not settings.demo_mode:
        _logger.warning(
            "JWT_SECRET_KEY is shorter than 32 characters — consider using a "
            "256-bit secret: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # Warn about DEMO_MODE
    if settings.demo_mode:
        _logger.warning(
            "DEMO_MODE is enabled - authentication is bypassed, "
            "all requests get ADMIN role. Do NOT use in production."
        )

    # Warn about missing methodology password
    if not settings.demo_mode and not settings.jwt_secret_key:
        _logger.warning(
            "JWT_SECRET_KEY not set - falling back to SUPABASE_KEY for JWT signing. "
            "Set JWT_SECRET_KEY for a dedicated signing secret."
        )

    _logger.info(f"Environment: {settings.environment}, Demo mode: {settings.demo_mode}")

    if testing_mode:
        _logger.info("TESTING mode: skipping background scheduler initialization")
        from app.api.devices import startup_event as devices_startup
        await devices_startup()
        return

    # Initialize Redis cache connection
    from app.services.cache_service import cache
    if cache.is_connected:
        print("Redis cache connected successfully")
    else:
        print("Redis cache unavailable - running without caching")

    # Initialize device manager with mock devices + building equipment
    from app.api.devices import startup_event as devices_startup
    await devices_startup()

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

    # Start AI recommendation generation job (runs every 10 minutes)
    # Scans ALL equipment and generates recommendations:
    # - Healthy equipment (>=90%): Optimization & preventive maintenance
    # - At-risk equipment (<90%): Maintenance & repair recommendations
    scheduler_service.add_recommendation_generation_job(interval_seconds=600)  # 10 minutes

    # Start model freshness check (runs daily)
    # Phase 45-01: Checks model age and R² score, auto-retrains stale models
    if hasattr(scheduler_service, "add_model_check_job"):
        scheduler_service.add_model_check_job(interval_seconds=86400)  # 24 hours

    # Start performance monitor (runs hourly)
    # Phase 45-01: Evaluates prediction accuracy against actual alerts
    if hasattr(scheduler_service, "add_performance_monitor_job"):
        scheduler_service.add_performance_monitor_job(interval_seconds=3600)  # 1 hour

    # BMS simulation service - DISABLED for demo stability
    # try:
    #     await simulation_service.start_simulation()
    #     print("BMS Simulation service started successfully")
    # except Exception as e:
    #     print(f"Failed to start simulation service: {e}")

    # Start health simulation service (writes to Supabase, triggers Clawd alerts)
    # Runs every hour between 08:00-17:00
    # DISABLED: Start manually via POST /api/simulation/health-sim/start
    # try:
    #     await health_simulation_service.start()
    #     print("Health simulation service started (hourly, 08:00-17:00)")
    # except Exception as e:
    #     print(f"Failed to start health simulation service: {e}")

    # SIMBIOT Concept Evolution connector
    # Auto-initializes when SIMBIOT_API_URL and SIMBIOT_API_KEY env vars are set
    if hasattr(simbiot_service, 'initialise_from_settings'):
        await simbiot_service.initialise_from_settings()
    elif settings.simbiot_api_url and settings.simbiot_api_key:
        try:
            from simbiot_concept import ConceptConfig
            config = ConceptConfig(
                api_url=settings.simbiot_api_url,
                api_key=settings.simbiot_api_key,
                username=settings.simbiot_username,
                password=settings.simbiot_password,
            )
            await simbiot_service.initialise(config)
            print(f"[SIMBIOT] Connected to {settings.simbiot_api_url}")
        except Exception as e:
            print(f"[SIMBIOT] Failed to initialize: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup background services on shutdown."""
    scheduler_service.stop()
    await health_simulation_service.stop()
    await simbiot_service.shutdown()


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "BMS Intelligence API", "version": settings.app_version}
