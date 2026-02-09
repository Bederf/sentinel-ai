"""Startup module for FastAPI application initialization.

This module contains all startup logic extracted from main.py to improve
maintainability and separation of concerns.

Components:
- routes: Router registration
- middleware: Middleware and exception handlers
- events: Startup/shutdown event handlers

Usage:
    from app.startup.routes import register_all_routes
    from app.startup.middleware import register_middleware, register_exception_handlers
    from app.startup.events import register_events

    app = FastAPI()
    register_exception_handlers(app)
    register_middleware(app)
    register_events(app)
    register_all_routes(app)
"""

from app.startup.routes import register_all_routes
from app.startup.middleware import register_middleware, register_exception_handlers
from app.startup.events import register_events

__all__ = [
    "register_all_routes",
    "register_middleware",
    "register_exception_handlers",
    "register_events",
]
