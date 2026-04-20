"""Prometheus HTTP request metrics middleware (Phase 127).

Captures request count, duration, and in-progress gauge for every HTTP request.
Path normalization prevents label cardinality explosion from dynamic path segments
(UUIDs, equipment codes, site IDs).
"""

from __future__ import annotations

import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Path normalization patterns — replace dynamic segments with {id}
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
# Equipment codes: S002-AHU-B1-001, S012-CHILLER-R-002, etc.
_EQUIP_RE = re.compile(r"S\d{3}-[A-Z]+-[A-Z0-9]+-\d{3}")
# Site IDs: site-002, site-012
_SITE_RE = re.compile(r"site-\d{3}")
# Generic numeric IDs at end of path segment
_NUMERIC_ID_RE = re.compile(r"/\d+(?=/|$)")

# Paths to skip entirely (high-frequency, low-value for metrics)
_SKIP_PATHS = frozenset({"/metrics", "/health", "/docs", "/openapi.json", "/favicon.ico"})


def _normalize_path(path: str) -> str:
    """Normalize a URL path to reduce Prometheus label cardinality.

    Replaces UUIDs, equipment codes, site IDs, and numeric IDs with {id}.
    """
    if path in _SKIP_PATHS:
        return path

    normalized = _UUID_RE.sub("{id}", path)
    normalized = _EQUIP_RE.sub("{id}", normalized)
    normalized = _SITE_RE.sub("{id}", normalized)
    normalized = _NUMERIC_ID_RE.sub("/{id}", normalized)
    return normalized


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that exports HTTP request metrics to Prometheus."""

    async def dispatch(self, request: Request, call_next) -> Response:
        from app.api.metrics import (
            sentinel_http_request_duration_seconds,
            sentinel_http_requests_in_progress,
            sentinel_http_requests_total,
        )

        path = _normalize_path(request.url.path)
        method = request.method

        # Skip metrics endpoint itself to avoid self-referential noise
        if path == "/metrics":
            return await call_next(request)

        sentinel_http_requests_in_progress.inc()
        start = time.perf_counter()
        status_code = 500  # Default if exception before response
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            duration = time.perf_counter() - start
            sentinel_http_requests_in_progress.dec()
            sentinel_http_requests_total.labels(method=method, path=path, status_code=str(status_code)).inc()
            sentinel_http_request_duration_seconds.labels(method=method, path=path).observe(duration)
