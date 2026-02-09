"""Startup module for recommendations API registration."""

import logging

logger = logging.getLogger(__name__)


def register_routers(app):
    """Register recommendation routers with FastAPI app.

    Args:
        app: FastAPI application instance
    """
    from app.api.recommendations import router

    app.include_router(router)
    logger.info("Registered recommendations router")
