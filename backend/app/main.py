"""BMS Intelligence Backend - FastAPI Application."""

from dotenv import load_dotenv

load_dotenv(override=True)  # Export .env vars to os.environ; override system env where .env takes precedence

from fastapi import FastAPI  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.startup.middleware import register_middleware, register_exception_handlers  # noqa: E402
from app.startup.events import register_events  # noqa: E402
from app.startup.routes import register_all_routes  # noqa: E402

# Configure structured logging (file handlers for Promtail/Loki)
setup_logging()

# =============================================================================
# Application Factory
# =============================================================================
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Building Management System Intelligence Platform",
)

# =============================================================================
# Application Initialization
# =============================================================================
# 1. Register exception handlers (rate limit, global error handler)
register_exception_handlers(app)

# 2. Register middleware (CORS, security headers, auth, audit, rate limiting)
register_middleware(app)

# 3. Register startup/shutdown event handlers
register_events(app)

# 4. Register API routes (70 routers across 4 domains)
register_all_routes(app)


# =============================================================================
# Root Endpoint
# =============================================================================
@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "BMS Intelligence API", "version": settings.app_version}
