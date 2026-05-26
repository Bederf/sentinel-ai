"""Middleware registration for FastAPI application.

This module contains all middleware setup and configuration, extracted
from main.py to improve maintainability and separation of concerns.
"""

import hmac
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config.settings import settings
from app.middleware.agent_security.middleware import AgentSecurityMiddleware, check_unmapped_routes
from app.middleware.audit_middleware import AuditMiddleware
from app.middleware.auth_middleware import _authenticate_request, _extract_ip_address
from app.middleware.error_sanitization import ErrorSanitizationMiddleware
from app.middleware.rate_limiter import limiter
from app.middleware.request_metrics import RequestMetricsMiddleware
from app.middleware.security_logging import SecurityLoggingMiddleware

_logger = logging.getLogger("sentinel.security")

# Paths that do not require authentication
_PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/access-request",
    "/api/auth/login/mfa-complete",
    "/api/auth/refresh",
    "/api/auth/register",
    "/api/auth/mfa/verify",
    "/api/auth/verify",
    "/api/auth/verify-admin-pin",
    "/api/auth/verify-settings-password",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/health",
    "/api/metrics",  # Prometheus scraping endpoint (network-isolated, no auth)
    "/api/health",
    "/api/lifecycle/status",  # Simulation status (frontend health check)
    "/api/chat/status",  # Chat service availability check (no sensitive data)
    "/api/events/stream",  # SSE stream (handles own ticket-based auth, no JWT in URL)
    "/api/events/health",  # SSE health check
    "/api/complaints/submit",  # Comfort complaint reporting (read-only, no controls)
    "/api/space/focus-sessions/9bd2f4c3-3359-4cd0-8769-1dab529248cf/close",  # TEMP: Close focus session
}
_PUBLIC_PREFIXES = (
    "/api/visits/qr/",  # Visitor QR code images — token is the secret, no JWT needed
    "/api/sentry-webhooks",  # Telegram bot callbacks (authenticated via webhook secret)
    "/api/sentry/telegram",  # Telegram bot webhook (authenticated via X-Telegram-Bot-Api-Secret-Token)
    "/api/sentry/email/",  # Sentry email intake (authenticated via X-Sentry-API-Key middleware)
    "/api/sentry-email/",  # Sentry email intake v2 — advisor strategy (authenticated via X-Sentry-API-Key in endpoint)
    "/api/emails/",  # Email cluster intake (authenticated via Bearer token in endpoint)
    "/api/whatsapp/",  # WhatsApp/Twilio webhooks (authenticated at webhook layer)
    "/api/telegram/",  # Telegram bot webhook (authenticated via X-Telegram-Bot-Api-Secret-Token)
    "/api/mcp/sse",  # MCP SSE transport for Claude Desktop (authenticated at MCP layer)
    "/api/mcp/openai",  # MCP OpenAI endpoints for ChatGPT/M365 Copilot (authenticated at MCP layer)
    "/api/lifecycle/",  # Lifecycle simulation status endpoints (frontend health checks)
    "/api/simbiot/",  # SIMBIOT onboarding wizard — public during site setup
    "/api/recommendations/",  # Recommendations endpoints (can be public for UI)
    "/api/municipal-billing/tariffs",  # Tariff schedules — read-only, scoped to site municipality
    "/api/webhooks/google/calendar",  # Google Calendar Pub/Sub push notifications (public — validated by channel ID)
    "/api/webhooks/graph/events",  # Microsoft Graph webhook notifications (public — validated by clientState)
    "/api/debug/",  # Debug endpoints for non-production inspection (guarded by environment=production check)
    "/api/buildings",  # Building/site data — used by SIMBIOT wizard and frontend during onboarding
    "/api/work-orders",  # Work order creation from optimization page (user-initiated, no JWT)
)
_PUBLIC_READ_PATHS = {
    "/api/block-bookings/alerts",
    "/api/block-bookings/bookings",
    "/api/space/ghost-findings",
    "/api/space/rightsizing-findings",
    "/api/space/focus-sessions",
    "/api/space/focus-analytics",
}
_PUBLIC_READ_PREFIXES = (
    "/api/concierge/rooms/",
    "/api/occupancy/analytics/",
)
_ADMIN_RATE_LIMIT_PER_MINUTE = 30
_admin_requests_by_ip: dict[str, list[datetime]] = defaultdict(list)
_SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}


def _is_public_read_request(path: str, method: str) -> bool:
    """Allow read-only Space/Concierge dashboard routes without requiring JWT."""
    if method.upper() not in _SAFE_HTTP_METHODS:
        return False
    return path in _PUBLIC_READ_PATHS or path.startswith(_PUBLIC_READ_PREFIXES)


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


def _should_rate_limit_admin_request(request: Request) -> bool:
    """Reserve admin throttling for mutating requests, not dashboard reads."""
    return request.method.upper() not in _SAFE_HTTP_METHODS


def _get_cors_headers(request: Request | None = None) -> dict:
    """Get standard CORS headers for error responses."""
    headers: dict[str, str] = {}
    if not settings.cors_origins:
        return headers

    # Check if request has an Origin header and if it's allowed
    origin = request.headers.get("origin") if request else None

    if origin and origin in settings.cors_origins:
        # Origin is in allowed list, allow it specifically
        headers["Access-Control-Allow-Origin"] = origin
    elif settings.cors_origins:
        # Allow the first configured origin as fallback
        headers["Access-Control-Allow-Origin"] = settings.cors_origins[0]

    # Always allow credentials and methods for configured origins
    headers["Access-Control-Allow-Credentials"] = "true"
    headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, x-site-id"

    return headers


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for the application."""

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """Return 429 with Retry-After header when rate limit exceeded."""
        # Audit: RATE_LIMIT_EXCEEDED (Phase 137-09)
        try:
            from app.security.audit_events import audit_rate_limit_exceeded

            source_ip = _extract_ip_address(request)
            audit_rate_limit_exceeded(path=str(request.url.path), source_ip=source_ip)
        except Exception:
            pass  # Audit failure must not block the 429 response

        headers = {"Retry-After": "60"}
        headers.update(_get_cors_headers(request))
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again later."},
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch-all handler that hides internals in production."""
        headers = _get_cors_headers(request)

        if settings.debug:
            # In debug mode, return full detail for developer convenience
            return JSONResponse(
                status_code=500,
                content={"detail": str(exc)},
                headers=headers,
            )
        # Log the real error server-side, return a generic message to the client
        _logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers=headers,
        )


def register_middleware(app: FastAPI) -> None:
    """Register all middleware for the application.

    Order matters - middleware is executed in reverse order of registration.
    The outermost middleware (registered first) sees the request first.
    """
    # Rate limiting (Phase 58-03 H-1)
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    # CORS (Phase 58-03 H-2) — restricted to configured origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "x-site-id"],
    )

    # Security headers (Phase 58-03 H-6, H-7)
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """Add standard security headers to every response."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # Global authentication enforcement (Phase 58-03 C-1)
    @app.middleware("http")
    async def enforce_authentication(request: Request, call_next):
        """Global auth enforcement -- all /api/ routes require auth unless whitelisted."""
        path = request.url.path

        # Allow CORS preflight requests (OPTIONS) without authentication
        # This must happen before other checks so CORS headers can be added
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip non-API routes and public paths
        if (
            path in _PUBLIC_PATHS
            or path.startswith(_PUBLIC_PREFIXES)
            or _is_public_read_request(path, request.method)
            or not path.startswith("/api/")
        ):
            return await call_next(request)

        # Allow any /api/* request with valid Sentry bot API key
        # The bot accesses /api/sites/, /api/sentry/, /api/alerts/, /api/equipment/,
        # /api/hvac/, /api/energy/, etc. for building monitoring.
        if settings.sentry_bot_api_key:
            api_key = request.headers.get("X-Sentry-API-Key", "")
            if hmac.compare_digest(api_key, settings.sentry_bot_api_key):
                _logger.info(f"Sentry bot API key authenticated for {path}")
                return await call_next(request)
            # If API key provided but wrong, reject immediately
            if api_key:
                _logger.warning(f"Invalid Sentry API key attempt on {path} from {_extract_ip_address(request)}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key"},
                    headers=_get_cors_headers(request),
                )
            # /api/sentry/* requires the API key (no fallback to JWT)
            if path.startswith("/api/sentry/"):
                _logger.warning(f"Missing Sentry API key for {path} from {_extract_ip_address(request)}")
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Sentry API key required"},
                    headers=_get_cors_headers(request),
                )

        # Universal Engine: All requests require real authentication.
        # Tests must provide JWT tokens or use service accounts (no magic TESTING bypass).
        # This ensures tests run against the actual production code path.
        auth_ctx = await _authenticate_request(request)
        if auth_ctx is None:
            # Log missing JWT for debugging misconfigured clients, forgotten test paths, integration errors
            source_ip = _extract_ip_address(request)
            _logger.error(
                f"Missing JWT authentication for {request.method} {path} from {source_ip}. "
                f"Authorization header missing or invalid. This may indicate: "
                f"(1) misconfigured client, (2) forgotten test path, (3) integration error. "
                f"Add JWT token or X-Sentry-API-Key header."
            )
            headers = {"WWW-Authenticate": "Bearer"}
            headers.update(_get_cors_headers(request))
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers=headers,
            )

        if auth_ctx.role.value == "admin" and _should_rate_limit_admin_request(request):
            source_ip = _extract_ip_address(request)
            admin_limit_response = _check_admin_rate_limit(source_ip)
            if admin_limit_response is not None:
                return admin_limit_response

        request.state.auth = auth_ctx
        return await call_next(request)

    # Error sanitization middleware (Phase 65-04 - prevents information disclosure)
    # In production, hides stack traces and internals from error responses
    if not settings.debug:
        app.add_middleware(ErrorSanitizationMiddleware)

    # Security logging middleware (Phase 63 - FSR compliance)
    # SecurityLoggingMiddleware runs first (outermost), captures all security events
    app.add_middleware(SecurityLoggingMiddleware)

    # Agent security middleware (Phase 120-05 — gates bot agent requests)
    # Runs AFTER enforce_authentication (so request.state.auth is available)
    # and BEFORE AuditMiddleware (so agent actions are audited).
    app.add_middleware(AgentSecurityMiddleware)

    # Audit middleware (existing - captures device control actions)
    app.add_middleware(AuditMiddleware)

    # Register agent security API router (confirmation + circuit breaker endpoints)
    from app.api.agent_security import router as agent_security_router

    app.include_router(agent_security_router, tags=["Agent Security"])

    # Cross-check registered routes against agent security PATH_TOOL_MAP
    # Logs warnings for unmapped agent-sensitive routes
    check_unmapped_routes(app)

    # Request metrics middleware (Phase 127 — outermost, captures full lifecycle)
    # Registered last so it wraps all other middleware (reverse execution order).
    app.add_middleware(RequestMetricsMiddleware)
