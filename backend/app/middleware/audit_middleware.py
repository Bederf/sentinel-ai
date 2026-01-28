"""Audit Middleware for FastAPI.

Middleware that intercepts control API calls and logs them to the audit system.
Integrates with existing authentication patterns and provides correlation IDs
for tracking related actions.
"""

import logging
import uuid
from typing import Callable, Dict, Any
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.services.audit_logger import AuditLogger
from app.models.audit_log import AuditActionType, AuditResultType

logger = logging.getLogger(__name__)


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

        # Extract user from request (demo: hardcoded, production: from auth)
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
                await self._log_successful_action(
                    request, response, user, correlation_id, request_start
                )
            else:  # Error
                await self._log_failed_action(
                    request, response, user, correlation_id, request_start
                )

            return response

        except Exception as e:
            # Log exception
            await self._log_exception(
                request, e, user, correlation_id, request_start
            )
            raise

    def _extract_user(self, request: Request) -> str:
        """Extract user from request (demo implementation)."""
        # Demo: Check for user header or default to "system"
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
            except:
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
        self,
        request: Request,
        response: Response,
        user: str,
        correlation_id: str,
        request_start: datetime
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

            # Log to audit system
            self.audit_logger.log_system_event(
                event_type=f"api_{action_type.lower()}",
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
                }
            )

            logger.info(
                f"Audit logged: {action_type} by {user} "
                f"(device: {device_id or 'N/A'}) - SUCCESS"
            )

        except Exception as e:
            logger.error(f"Failed to log successful action: {e}")

    async def _log_failed_action(
        self,
        request: Request,
        response: Response,
        user: str,
        correlation_id: str,
        request_start: datetime
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
            except:
                pass

            self.audit_logger.log_system_event(
                event_type=f"api_{action_type.lower()}",
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
                }
            )

            logger.warning(
                f"Audit logged: {action_type} by {user} "
                f"(device: {device_id or 'N/A'}) - FAILED: {error_message}"
            )

        except Exception as e:
            logger.error(f"Failed to log failed action: {e}")

    async def _log_exception(
        self,
        request: Request,
        exception: Exception,
        user: str,
        correlation_id: str,
        request_start: datetime
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
                }
            )

            logger.error(
                f"Audit logged: {action_type} by {user} - EXCEPTION: {exception}"
            )

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

    async def _extract_request_data(self, request: Request) -> Dict[str, Any]:
        """Extract request data for auditing."""
        try:
            # For GET requests, use query params
            if request.method == "GET":
                return dict(request.query_params)

            # For other methods, try to get JSON body
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.json()
                    if isinstance(body, dict):
                        # Sanitize sensitive data
                        sanitized = body.copy()
                        for key in ["password", "token", "secret", "key"]:
                            if key in sanitized:
                                sanitized[key] = "***REDACTED***"
                        return sanitized
                except:
                    pass

            return {"content_type": content_type}

        except Exception as e:
            logger.warning(f"Failed to extract request data: {e}")
            return {"error": "failed_to_extract"}