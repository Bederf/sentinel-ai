"""
Production Error Sanitization Middleware for SENTINEL BMS Platform.

Prevents information disclosure through error messages in production.
Ported from AimTheLaw error_sanitization.py, adapted for SENTINEL.

NOT registered globally - opt-in per deployment configuration.

FSR Domain: 4.7 - Logical Access Control (information disclosure prevention)
"""

import logging
from typing import Optional

from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config.settings import settings

logger = logging.getLogger(__name__)


class ErrorSanitizationMiddleware(BaseHTTPMiddleware):
    """Middleware to sanitize error messages in production.

    In debug mode, full error details are returned.
    In production, sensitive information is stripped from error responses.
    """

    def __init__(self, app, debug_mode: Optional[bool] = None):
        super().__init__(app)
        self.debug_mode = debug_mode if debug_mode is not None else settings.debug

    async def dispatch(self, request: Request, call_next) -> Response:
        """Intercept and sanitize error responses."""
        try:
            response = await call_next(request)
            return response
        except HTTPException as http_exc:
            return self._create_sanitized_response(http_exc.status_code, http_exc.detail, request)
        except Exception as exc:
            logger.error(
                f"Unhandled exception in {request.url.path}: {type(exc).__name__}",
                exc_info=self.debug_mode,
            )
            return self._create_sanitized_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                str(exc) if self.debug_mode else "Internal server error",
                request,
            )

    def _create_sanitized_response(self, status_code: int, detail: str, request: Request) -> JSONResponse:
        """Create a sanitized error response."""
        if not self.debug_mode:
            detail = self._sanitize_error_message(status_code, detail)

        logger.warning(
            f"API Error: {status_code} on {request.url.path} - "
            f"User-Agent: {request.headers.get('user-agent', 'unknown')} - "
            f"IP: {request.client.host if request.client else 'unknown'}"
        )

        response_data = {
            "error": detail,
            "status_code": status_code,
            "path": str(request.url.path),
        }

        if hasattr(request.state, "request_id"):
            response_data["request_id"] = request.state.request_id

        return JSONResponse(status_code=status_code, content=response_data)

    def _sanitize_error_message(self, status_code: int, detail: str) -> str:
        """Sanitize error messages for production."""
        safe_messages = {
            400: "Invalid request data",
            401: "Authentication required",
            403: "Access denied",
            404: "Resource not found",
            405: "Method not allowed",
            409: "Resource conflict",
            422: "Invalid input data",
            429: "Rate limit exceeded",
            500: "Internal server error",
            501: "Not implemented",
            502: "Bad gateway",
            503: "Service unavailable",
        }

        # For auth errors, preserve some detail
        if status_code in [401, 403]:
            if any(keyword in detail.lower() for keyword in ["token", "expired", "invalid", "required"]):
                return detail

        # For validation errors, provide limited detail
        if status_code == 422:
            if "validation error" in detail.lower():
                return "Request validation failed"

        # For client errors (4xx), use safe message if detail looks sensitive
        if 400 <= status_code < 500:
            if len(detail) < 100 and not self._contains_sensitive_info(detail):
                return detail
            return safe_messages.get(status_code, "Client error")

        # For server errors (5xx), always use safe message
        if status_code >= 500:
            return safe_messages.get(status_code, "Server error")

        return detail

    def _contains_sensitive_info(self, message: str) -> bool:
        """Check if error message contains sensitive information."""
        sensitive_keywords = [
            "database",
            "sql",
            "connection",
            "password",
            "secret",
            "key",
            "token",
            "credential",
            "path",
            "file",
            "directory",
            "system",
            "internal",
            "config",
            "environment",
            "variable",
            "stack trace",
            "traceback",
            "exception",
            "error in",
            "failed to",
            "unable to connect",
            "supabase",
            "postgresql",
            "influxdb",
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in sensitive_keywords)


class SafeHTTPException(HTTPException):
    """HTTP Exception that's safe to show to users in production.

    Use this when you want to return a specific error message
    that won't be sanitized by ErrorSanitizationMiddleware.
    """

    pass
