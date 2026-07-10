"""Startup module for recommendations API registration."""

import logging

logger = logging.getLogger(__name__)


def register_routers(app):
    """Register recommendation and progression engine routers with FastAPI app.

    Args:
        app: FastAPI application instance
    """
    from app.api.recommendations import router

    app.include_router(router)
    logger.info("Registered recommendations router")

    from app.api.progression import router as progression_router

    app.include_router(progression_router)
    logger.info("Registered progression engine API router")
