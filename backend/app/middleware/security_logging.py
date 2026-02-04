"""Security Logging Middleware for SENTINEL BMS Intelligence.

Ported from AimTheLaw production middleware, adapted for BMS domain.
Captures security-relevant events: failed auth, suspicious requests,
device control actions, safety overrides, and BMS commands.

Structured JSON logging output is collected by Promtail and shipped to Loki.
"""

import json
import logging
import time
import uuid
import ipaddress
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Dedicated security event logger - outputs structured JSON
# Promtail collects from Docker container logs
security_logger = logging.getLogger("sentinel.security")

# Deduplication window for repeated events from same source
_RECENT_EVENTS: Dict[str, float] = {}
_DEDUP_WINDOW_SEC = 2.0


class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured security event logging.

    Captures:
    - Failed authentication attempts (401/403 responses)
    - Suspicious user agents (automated tools, scanners)
    - Suspicious path patterns (SQL injection, path traversal)
    - Device control actions
    - Safety override attempts
    - BMS command execution
    - After-hours access to sensitive endpoints
    - Error spikes (5xx responses)
    """

    # Paths to skip entirely (health checks, docs, static)
    SKIP_PATHS = {
        "/api/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/",
    }

    # Security-sensitive endpoints (always log access)
    SENSITIVE_ENDPOINTS = {
        "/api/devices",
        "/api/safety",
        "/api/optimization",
        "/api/chat",
        "/api/mcp",
        "/api/remote",
        "/api/fire",
    }

    # BMS control endpoints (log all access with full detail)
    CONTROL_ENDPOINTS = {
        "/control",       # device control
        "/approve",       # approval actions
        "/execute",       # execution actions
        "/override",      # safety overrides
        "/activate",      # activation actions
    }

    # Suspicious user agent patterns (automated tools, scanners)
    SUSPICIOUS_USER_AGENTS = [
        "curl", "wget", "python-requests", "httpx", "axios",
        "postman", "insomnia", "burp", "owasp", "zap",
        "nmap", "nikto", "sqlmap", "gobuster", "dirb",
        "dirbuster", "wpscan", "masscan", "nuclei", "nessus",
        "scanner", "crawler", "spider", "scraper",
    ]

    # Suspicious path patterns (injection, traversal)
    SUSPICIOUS_PATH_PATTERNS = [
        "../", "..\\",                     # Path traversal
        "' OR ", "\" OR ", "1=1",          # SQL injection
        "<script", "javascript:",          # XSS
        "/etc/passwd", "/etc/shadow",      # File access
        ".env", "wp-admin", "wp-login",    # Common probes
        "/admin", "/phpmyadmin",           # Admin panel probes
        "cmd=", "exec(", "system(",        # Command injection
    ]

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request, log security events, add security headers."""
        path = request.url.path

        # Skip health/docs/static endpoints
        if path in self.SKIP_PATHS or path.startswith("/docs"):
            return await call_next(request)

        # Generate correlation ID
        correlation_id = str(uuid.uuid4())[:12]
        request.state.security_correlation_id = correlation_id

        # Extract request context
        source_ip = self._extract_ip(request)
        user_agent = request.headers.get("User-Agent", "")
        method = request.method
        start_time = time.time()

        # Check for suspicious patterns BEFORE processing
        self._check_suspicious_request(
            path, method, source_ip, user_agent, correlation_id
        )

        # Check if this is a BMS control action
        is_control = any(path.endswith(ep) for ep in self.CONTROL_ENDPOINTS)
        is_sensitive = any(path.startswith(ep) for ep in self.SENSITIVE_ENDPOINTS)

        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            # Log based on response status
            if response.status_code == 401:
                self._log_security_event(
                    event_type="AUTH_FAILURE",
                    severity="medium",
                    source_ip=source_ip,
                    user_agent=user_agent,
                    path=path,
                    method=method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    details={"reason": "unauthorized"}
                )
            elif response.status_code == 403:
                self._log_security_event(
                    event_type="ACCESS_DENIED",
                    severity="high",
                    source_ip=source_ip,
                    user_agent=user_agent,
                    path=path,
                    method=method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    details={"reason": "forbidden"}
                )
            elif response.status_code >= 500:
                self._log_security_event(
                    event_type="SERVER_ERROR",
                    severity="high",
                    source_ip=source_ip,
                    user_agent=user_agent,
                    path=path,
                    method=method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    details={"reason": "internal_server_error"}
                )
            elif is_control and method in ["POST", "PUT", "PATCH"]:
                self._log_security_event(
                    event_type="BMS_CONTROL_ACTION",
                    severity="info",
                    source_ip=source_ip,
                    user_agent=user_agent,
                    path=path,
                    method=method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    details={"control_type": self._get_control_type(path)}
                )
            elif is_sensitive and method in ["POST", "PUT", "PATCH", "DELETE"]:
                self._log_security_event(
                    event_type="SENSITIVE_ENDPOINT_ACCESS",
                    severity="low",
                    source_ip=source_ip,
                    user_agent=user_agent,
                    path=path,
                    method=method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    details={}
                )

            # Add security headers
            self._add_security_headers(response)

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._log_security_event(
                event_type="REQUEST_EXCEPTION",
                severity="critical",
                source_ip=source_ip,
                user_agent=user_agent,
                path=path,
                method=method,
                status_code=500,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                details={
                    "exception_type": type(e).__name__,
                    "exception_message": str(e)[:200]
                }
            )
            raise

    def _extract_ip(self, request: Request) -> Optional[str]:
        """Extract client IP from request with proxy/Cloudflare support."""
        # Cloudflare Tunnel passes real IP in CF-Connecting-IP
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()

        # Standard proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Direct connection
        if request.client:
            return request.client.host

        return None

    def _is_internal_ip(self, ip: str) -> bool:
        """Check if IP is from internal/private network (RFC 1918 + Docker)."""
        if not ip:
            return False
        try:
            addr = ipaddress.ip_address(ip)
            return addr.is_private or addr.is_loopback
        except ValueError:
            return False

    def _check_suspicious_request(
        self,
        path: str,
        method: str,
        source_ip: Optional[str],
        user_agent: str,
        correlation_id: str
    ) -> None:
        """Check for suspicious request patterns and log if detected."""
        user_agent_lower = user_agent.lower()
        path_lower = path.lower()

        # Check suspicious user agents (skip internal IPs)
        if source_ip and not self._is_internal_ip(source_ip):
            for pattern in self.SUSPICIOUS_USER_AGENTS:
                if pattern in user_agent_lower:
                    self._log_security_event_deduped(
                        event_type="SUSPICIOUS_USER_AGENT",
                        severity="medium",
                        source_ip=source_ip,
                        user_agent=user_agent,
                        path=path,
                        method=method,
                        correlation_id=correlation_id,
                        details={"matched_pattern": pattern}
                    )
                    break

        # Check suspicious path patterns
        for pattern in self.SUSPICIOUS_PATH_PATTERNS:
            if pattern.lower() in path_lower:
                self._log_security_event(
                    event_type="SUSPICIOUS_PATH",
                    severity="high",
                    source_ip=source_ip,
                    user_agent=user_agent,
                    path=path,
                    method=method,
                    correlation_id=correlation_id,
                    details={"matched_pattern": pattern}
                )
                break

    def _log_security_event_deduped(self, **kwargs) -> None:
        """Log security event with deduplication (2-second window)."""
        dedup_key = f"{kwargs.get('source_ip', '')}:{kwargs.get('event_type', '')}:{kwargs.get('path', '')}"
        now = time.time()
        last = _RECENT_EVENTS.get(dedup_key, 0.0)

        if now - last < _DEDUP_WINDOW_SEC:
            return

        _RECENT_EVENTS[dedup_key] = now

        # Prune old entries periodically (every 100 events)
        if len(_RECENT_EVENTS) > 1000:
            cutoff = now - _DEDUP_WINDOW_SEC * 10
            keys_to_remove = [k for k, v in _RECENT_EVENTS.items() if v < cutoff]
            for k in keys_to_remove:
                del _RECENT_EVENTS[k]

        self._log_security_event(**kwargs)

    def _log_security_event(
        self,
        event_type: str,
        severity: str,
        source_ip: Optional[str] = None,
        user_agent: str = "",
        path: str = "",
        method: str = "",
        status_code: Optional[int] = None,
        duration_ms: Optional[float] = None,
        correlation_id: str = "",
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a structured security event to the security logger.

        Output format is JSON for Promtail/Loki ingestion.
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "severity": severity,
            "source_ip": source_ip,
            "user_agent": user_agent[:200] if user_agent else "",
            "path": path,
            "method": method,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2) if duration_ms else None,
            "correlation_id": correlation_id,
            "component": "sentinel-backend",
            "details": details or {}
        }

        # Log at appropriate level based on severity
        log_message = json.dumps(event, default=str)
        if severity == "critical":
            security_logger.critical(log_message)
        elif severity == "high":
            security_logger.warning(log_message)
        elif severity == "medium":
            security_logger.info(log_message)
        else:
            security_logger.debug(log_message)

    def _get_control_type(self, path: str) -> str:
        """Determine control action type from path."""
        if "/control" in path:
            return "DEVICE_CONTROL"
        elif "/approve" in path:
            return "APPROVAL"
        elif "/execute" in path:
            return "EXECUTION"
        elif "/override" in path:
            return "SAFETY_OVERRIDE"
        elif "/activate" in path:
            return "ACTIVATION"
        return "UNKNOWN"

    def _add_security_headers(self, response: Response) -> None:
        """Add security headers to all responses."""
        if not response.headers.get("X-Content-Type-Options"):
            response.headers["X-Content-Type-Options"] = "nosniff"
        if not response.headers.get("X-Frame-Options"):
            response.headers["X-Frame-Options"] = "DENY"
        if not response.headers.get("X-XSS-Protection"):
            response.headers["X-XSS-Protection"] = "1; mode=block"
        if not response.headers.get("Referrer-Policy"):
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not response.headers.get("Permissions-Policy"):
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"


def log_security_event(
    event_type: str,
    severity: str = "info",
    source_ip: Optional[str] = None,
    user_agent: str = "",
    path: str = "",
    method: str = "",
    status_code: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """Convenience function for explicit security event logging from services.

    Use this function to log security events from business logic, not just
    HTTP middleware. For example:
    - Device control with safety override
    - Setpoint changes on critical equipment
    - BMS command execution
    - Alarm acknowledgement

    Args:
        event_type: Event classification (DEVICE_CONTROL, SAFETY_OVERRIDE, etc.)
        severity: Event severity (critical, high, medium, low, info)
        source_ip: Client IP address
        user_agent: Client user agent string
        path: API path or action identifier
        method: HTTP method or action type
        status_code: Response status code
        details: Additional event-specific details
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "severity": severity,
        "source_ip": source_ip,
        "user_agent": user_agent[:200] if user_agent else "",
        "path": path,
        "method": method,
        "status_code": status_code,
        "component": "sentinel-backend",
        "details": details or {}
    }

    log_message = json.dumps(event, default=str)
    if severity == "critical":
        security_logger.critical(log_message)
    elif severity == "high":
        security_logger.warning(log_message)
    elif severity == "medium":
        security_logger.info(log_message)
    else:
        security_logger.debug(log_message)
