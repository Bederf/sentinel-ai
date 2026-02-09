"""BMS Intelligence Backend - FastAPI Application."""

from collections import defaultdict
from datetime import datetime, timedelta
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config.settings import settings
from app.middleware.auth_middleware import _authenticate_request, _extract_ip_address
from app.middleware.rate_limiter import limiter

# Import router registrars (domain-based router organization)
from app.api.registrars.core import register_core_routers
from app.api.registrars.building import register_building_routers
from app.api.registrars.operations import register_operations_routers
from app.api.registrars.analytics import register_analytics_routers
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
    "/api/auth/refresh",
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
_ADMIN_RATE_LIMIT_PER_MINUTE = 30
_admin_requests_by_ip: dict[str, list[datetime]] = defaultdict(list)


def _check_admin_rate_limit(source_ip: str) -> JSONResponse | None:
    """Enforce admin API limit of 30 requests per minute per IP."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=1)
    recent = [t for t in _admin_requests_by_ip[source_ip] if t > cutoff]
    _admin_requests_by_ip[source_ip] = recent

    if len(recent) >= _ADMIN_RATE_LIMIT_PER_MINUTE:
        retry_after_seconds = max(1, int((recent[0] + timedelta(minutes=1) - now).total_seconds()))
        return JSONResponse(
            status_code=429,
            content={"detail": "Admin API rate limit exceeded. Please try again later."},
            headers={"Retry-After": str(retry_after_seconds)},
        )

    recent.append(now)
    return None


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

    if auth_ctx.role.value == "admin":
        source_ip = _extract_ip_address(request)
        admin_limit_response = _check_admin_rate_limit(source_ip)
        if admin_limit_response is not None:
            return admin_limit_response

    request.state.auth = auth_ctx
    return await call_next(request)


# Add security logging middleware (Phase 63 - FSR compliance)
# SecurityLoggingMiddleware runs first (outermost), captures all security events
app.add_middleware(SecurityLoggingMiddleware)

# Add audit middleware (existing - captures device control actions)
app.add_middleware(AuditMiddleware)

# =============================================================================
# Router Registration (Phase 67-01: Decompose main.py)
# =============================================================================
# Register API routers by domain using registrar modules.
# This reduces main.py from 83 individual include_router() calls to 4
# registrar calls, improving maintainability and organization.
# =============================================================================
register_core_routers(app)
register_building_routers(app)
register_operations_routers(app)
register_analytics_routers(app)


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
