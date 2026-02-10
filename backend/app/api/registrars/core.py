"""
Core API router registrar.

Registers core API routers for authentication, settings, sites, and health.
"""

from fastapi import FastAPI

from app.api import health, sites, settings as settings_api, settings_db, system_health
from app.api import auth, user_access, login_audit, mfa, cache


def register_core_routers(app: FastAPI) -> None:
    """Register core API routers (auth, settings, sites, cache, health)."""
    # Health and monitoring
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(system_health.router, tags=["system-health"])
    app.include_router(cache.router, tags=["cache"])

    # Sites (core entity)
    app.include_router(sites.router, prefix="/api", tags=["sites"])

    # Settings (JSON-based deprecated + Supabase-based new)
    app.include_router(settings_api.router, prefix="/api", tags=["settings"])
    app.include_router(settings_db.router, prefix="/api/db", tags=["settings-db"])

    # Authentication and authorization
    app.include_router(auth.router, tags=["auth"])
    app.include_router(user_access.router, tags=["user-access"])
    app.include_router(login_audit.router, tags=["login-audit"])
    app.include_router(mfa.router, tags=["mfa"])
