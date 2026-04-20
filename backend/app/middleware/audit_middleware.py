"""Audit Middleware for FastAPI.

Middleware that intercepts control API calls and logs them to the audit system.
Integrates with existing authentication patterns and provides correlation IDs
for tracking related actions.
"""

import logging
import re
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.models.audit_log import AuditResultType
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensitive data sanitisation (Phase 58-04 M-4 + Phase 65-04 PII masking)
# ---------------------------------------------------------------------------
_SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "jwt",
    "credential",
    "credit_card",
    "ssn",
    "email",
}

# Email regex for PII masking
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _sanitize_email(email: str) -> str:
    """Mask email address for logging.

    Example: user@example.com -> u***r@e***.com

    Args:
        email: Email address to sanitize

    Returns:
        Masked email address
    """
    if not email or "@" not in email:
        return "***"

    local, domain = email.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]

    if len(domain) <= 1:
        masked_domain = "*"
    else:
        # Mask domain but keep TLD
        parts = domain.rsplit(".", 1)
        if len(parts) == 2:
            masked_domain = parts[0][0] + "*" * (len(parts[0]) - 1) + "." + parts[1]
        else:
            masked_domain = parts[0][0] + "*" * (len(parts[0]) - 1)

    return f"{masked_local}@{masked_domain}"


def _sanitize_log_data(data: dict) -> dict:
    """Recursively redact values whose keys look sensitive.

    Keys are matched case-insensitively against _SENSITIVE_KEYS.
    Email addresses are masked using _sanitize_email.
    Nested dicts are sanitised recursively; other types are left as-is.
    """
    sanitized: dict = {}
    for k, v in data.items():
        if k.lower() in _SENSITIVE_KEYS:
            # Special handling for email fields
            if k.lower() == "email" and isinstance(v, str):
                sanitized[k] = _sanitize_email(v)
            else:
                sanitized[k] = "***REDACTED***"
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_log_data(v)
        elif isinstance(v, str):
            # Mask email addresses found in string values
            sanitized[k] = _EMAIL_PATTERN.sub(lambda m: _sanitize_email(m.group()), v)
        else:
            sanitized[k] = v
    return sanitized


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware for auditing API requests."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.audit_logger = AuditLogger()
        self.control_endpoints = {
            "/api/devices/{id}/control": "DEVICE_CONTROL",
            "/api/chat": "CHAT_COMMAND",
            "/api/work-orders": "WORK_ORDER_CREATION",
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and audit control actions."""
        # Generate correlation ID for this request chain
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        # Extract user from request (local fallback vs production auth)
        user = self._extract_user(request)

        # Skip audit for non-control endpoints
        if not self._is_control_endpoint(request.url.path, request.method):
            return await call_next(request)

        # Log request start
        request_start = datetime.now()
        logger.debug(f"Auditing request: {request.method} {request.url.path}")

        try:
            # Process request
            response = await call_next(request)

            # Log successful control action
            if response.status_code < 400:  # Success
                await self._log_successful_action(request, response, user, correlation_id, request_start)
            else:  # Error
                await self._log_failed_action(request, response, user, correlation_id, request_start)

            return response

        except Exception as e:
            # Log exception
            await self._log_exception(request, e, user, correlation_id, request_start)
            raise

    def _extract_user(self, request: Request) -> str:
        """Extract user from request, with bot agent detection (Phase 120-03).

        If the request is from a bot agent (AuthContext.is_bot_agent), the
        user_id is prefixed with "bot:" so audit logs clearly distinguish
        bot traffic from human traffic.
        """
        # Phase 120-03: Check AuthContext for bot agent identity
        auth_ctx = getattr(getattr(request, "state", None), "auth", None)
        if auth_ctx is not None:
            user_id = getattr(auth_ctx, "user_id", None)
            is_bot = getattr(auth_ctx, "is_bot_agent", False)
            if user_id:
                if is_bot and not user_id.startswith("bot:"):
                    return f"bot:{user_id}"
                return user_id

        # Fallback: Check for user header or default to "system"
        user_header = request.headers.get("X-User-Id")
        if user_header:
            return user_header

        # For chat requests, try to get from query params
        if request.url.path == "/api/chat":
            try:
                # Try to parse JSON body for user
                if hasattr(request, "_json"):
                    body = request._json
                    if isinstance(body, dict) and "user_id" in body:
                        return body["user_id"]
            except Exception:
                pass

        return "system"  # Default for automated/system actions

    def _is_control_endpoint(self, path: str, method: str) -> bool:
        """Check if endpoint is a control action that should be audited."""
        # Device control endpoints
        if path.startswith("/api/devices/") and path.endswith("/control"):
            return method in ["POST", "PUT", "PATCH"]

        # Chat commands
        if path == "/api/chat" and method == "POST":
            return True

        # Work order creation
        if path == "/api/work-orders" and method == "POST":
            return True

        return False

    async def _log_successful_action(
        self, request: Request, response: Response, user: str, correlation_id: str, request_start: datetime
    ) -> None:
        """Log successful control action."""
        try:
            # Determine action type based on endpoint
            action_type = self._get_action_type(request.url.path)

            # Extract device ID from path if applicable
            device_id = None
            if request.url.path.startswith("/api/devices/"):
                # Extract device ID from /api/devices/{id}/control
                parts = request.url.path.split("/")
                if len(parts) >= 4:
                    device_id = parts[3]

            # Extract request data
            request_data = await self._extract_request_data(request)

            # Calculate duration
            duration_ms = (datetime.now() - request_start).total_seconds() * 1000

            # Phase 120-03: Determine agent type for audit metadata
            auth_ctx = getattr(getattr(request, "state", None), "auth", None)
            agent_type = "bot_agent" if (auth_ctx and getattr(auth_ctx, "is_bot_agent", False)) else "human"
            event_type = f"bot_{action_type.lower()}" if agent_type == "bot_agent" else f"api_{action_type.lower()}"

            # Log to audit system
            self.audit_logger.log_system_event(
                event_type=event_type,
                user=user,
                result=AuditResultType.SUCCESS,
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "device_id": device_id,
                    "request_data": request_data,
                    "response_status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "correlation_id": correlation_id,
                    "agent_type": agent_type,
                },
            )

            logger.info(
                f"Audit logged: {action_type} by {user} (device: {device_id or 'N/A'}, agent: {agent_type}) - SUCCESS"
            )

        except Exception as e:
            logger.error(f"Failed to log successful action: {e}")

    async def _log_failed_action(
        self, request: Request, response: Response, user: str, correlation_id: str, request_start: datetime
    ) -> None:
        """Log failed control action."""
        try:
            action_type = self._get_action_type(request.url.path)
            device_id = None

            if request.url.path.startswith("/api/devices/"):
                parts = request.url.path.split("/")
                if len(parts) >= 4:
                    device_id = parts[3]

            request_data = await self._extract_request_data(request)
            duration_ms = (datetime.now() - request_start).total_seconds() * 1000

            # Try to extract error message from response body
            error_message = f"HTTP {response.status_code}"
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                # Reset iterator for downstream use (must be async iterator)
                async def body_iterator():
                    yield body

                response.body_iterator = body_iterator()

                if body:
                    import json

                    error_data = json.loads(body.decode())
                    error_message = error_data.get("detail", error_message)
            except Exception:
                pass

            # Phase 120-03: Determine agent type for audit metadata
            auth_ctx = getattr(getattr(request, "state", None), "auth", None)
            agent_type = "bot_agent" if (auth_ctx and getattr(auth_ctx, "is_bot_agent", False)) else "human"
            event_type = f"bot_{action_type.lower()}" if agent_type == "bot_agent" else f"api_{action_type.lower()}"

            self.audit_logger.log_system_event(
                event_type=event_type,
                user=user,
                result=AuditResultType.FAILED,
                error_message=error_message,
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "device_id": device_id,
                    "request_data": request_data,
                    "response_status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "correlation_id": correlation_id,
                    "agent_type": agent_type,
                },
            )

            logger.warning(
                f"Audit logged: {action_type} by {user} "
                f"(device: {device_id or 'N/A'}, agent: {agent_type}) "
                f"- FAILED: {error_message}"
            )

        except Exception as e:
            logger.error(f"Failed to log failed action: {e}")

    async def _log_exception(
        self, request: Request, exception: Exception, user: str, correlation_id: str, request_start: datetime
    ) -> None:
        """Log exception during request processing."""
        try:
            action_type = self._get_action_type(request.url.path)
            duration_ms = (datetime.now() - request_start).total_seconds() * 1000

            self.audit_logger.log_system_event(
                event_type=f"api_{action_type.lower()}_exception",
                user=user,
                result=AuditResultType.FAILED,
                error_message=str(exception),
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "exception_type": type(exception).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "correlation_id": correlation_id,
                },
            )

            logger.error(f"Audit logged: {action_type} by {user} - EXCEPTION: {exception}")

        except Exception as e:
            logger.error(f"Failed to log exception: {e}")

    def _get_action_type(self, path: str) -> str:
        """Get action type from path."""
        if path.startswith("/api/devices/") and path.endswith("/control"):
            return "DEVICE_CONTROL"
        elif path == "/api/chat":
            return "CHAT_COMMAND"
        elif path == "/api/work-orders":
            return "WORK_ORDER_CREATION"
        else:
            return "API_REQUEST"

    async def _extract_request_data(self, request: Request) -> dict[str, Any]:
        """Extract request data for auditing.

        Phase 58-04 M-4: All extracted data is run through _sanitize_log_data
        to strip tokens, passwords, API keys, and other sensitive values.
        """
        try:
            # For GET requests, use query params
            if request.method == "GET":
                return _sanitize_log_data(dict(request.query_params))

            # For other methods, try to get JSON body
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.json()
                    if isinstance(body, dict):
                        return _sanitize_log_data(body)
                except Exception:
                    pass

            return {"content_type": content_type}

        except Exception as e:
            logger.warning(f"Failed to extract request data: {e}")
            return {"error": "failed_to_extract"}
