"""Middleware registration for FastAPI application.

This module contains all middleware setup and configuration, extracted
from main.py to improve maintainability and separation of concerns.
"""

from collections import defaultdict
from datetime import datetime, timedelta
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config.settings import settings
from app.middleware.auth_middleware import _authenticate_request, _extract_ip_address
from app.middleware.rate_limiter import limiter
from app.middleware.audit_middleware import AuditMiddleware
from app.middleware.security_logging import SecurityLoggingMiddleware
from app.middleware.error_sanitization import ErrorSanitizationMiddleware
from app.middleware.agent_security.middleware import AgentSecurityMiddleware, check_unmapped_routes
from app.middleware.request_metrics import RequestMetricsMiddleware

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
    "/docs",
    "/openapi.json",
    "/redoc",
    "/health",
    "/api/health",
    "/api/lifecycle/status",  # Simulation status (frontend health check)
    "/api/events/stream",  # SSE stream (handles own ticket-based auth, no JWT in URL)
    "/api/events/health",  # SSE health check
}
_PUBLIC_PREFIXES = (
    "/api/sentry-webhooks",  # Telegram bot callbacks (authenticated via webhook secret)
    "/api/mcp/sse",  # MCP SSE transport for Claude Desktop (authenticated at MCP layer)
    "/api/mcp/openai",  # MCP OpenAI endpoints for ChatGPT/M365 Copilot (authenticated at MCP layer)
    "/api/lifecycle/",  # Lifecycle simulation status endpoints (frontend health checks)
    "/api/recommendations/",  # Recommendations endpoints (can be public for UI)
)
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


def _get_cors_headers(request: Request | None = None) -> dict:
    """Get standard CORS headers for error responses."""
    headers = {}
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
    headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"

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

        headers = {"Retry-After": str(exc.retry_after)}
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
        allow_headers=["Authorization", "Content-Type"],
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
        if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES) or not path.startswith("/api/"):
            return await call_next(request)

        # Allow /api/sites/* with Sentry bot API key
        if path.startswith("/api/sites/") and settings.sentry_bot_api_key:
            api_key = request.headers.get("X-Sentry-API-Key", "")
            if api_key == settings.sentry_bot_api_key:
                _logger.info(f"Sentry bot API key authenticated for {path}")
                return await call_next(request)
            # If API key provided but wrong, log it as security event
            if api_key:
                _logger.warning(f"Invalid Sentry API key attempt on {path} from {_extract_ip_address(request)}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key"},
                    headers=_get_cors_headers(request),
                )

        # Allow /api/sentry/* with Sentry bot API key
        # SECURITY FIX: Phase 100 - All Sentry endpoints must be authenticated with API key
        if path.startswith("/api/sentry/") and settings.sentry_bot_api_key:
            api_key = request.headers.get("X-Sentry-API-Key", "")
            if api_key == settings.sentry_bot_api_key:
                _logger.info(f"Sentry bot API key authenticated for {path}")
                return await call_next(request)
            # If API key provided but wrong, log it as security event
            if api_key:
                _logger.warning(f"Invalid Sentry API key attempt on {path} from {_extract_ip_address(request)}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key"},
                    headers=_get_cors_headers(request),
                )
            # No API key provided - deny access
            _logger.warning(f"Missing Sentry API key for {path} from {_extract_ip_address(request)}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Sentry API key required"},
                headers=_get_cors_headers(request),
            )

        # Require real authentication
        auth_ctx = await _authenticate_request(request)
        if auth_ctx is None:
            headers = {"WWW-Authenticate": "Bearer"}
            headers.update(_get_cors_headers(request))
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers=headers,
            )

        if auth_ctx.role.value == "admin":
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
