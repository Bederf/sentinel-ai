"""Shared rate limiter configuration.

Provides a single Limiter instance for all routers so decorators and middleware
use the same state and key function.
"""

from fastapi import Request
from slowapi import Limiter


def get_client_ip(request: Request) -> str:
    """Extract client IP address, preferring proxy headers."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_client_ip, default_limits=["200/minute"])
