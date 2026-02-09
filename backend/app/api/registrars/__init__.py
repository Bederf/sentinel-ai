"""
Router registrars for organizing API endpoints.

This package provides domain-based registrar modules that group related
API routers together, reducing the complexity of main.py.

Usage:
    from app.api.registrars.core import register_core_routers
    from app.api.registrars.building import register_building_routers
    from app.api.registrars.operations import register_operations_routers
    from app.api.registrars.analytics import register_analytics_routers

    app = FastAPI()
    register_core_routers(app)
    register_building_routers(app)
    register_operations_routers(app)
    register_analytics_routers(app)
"""

from app.api.registrars.core import register_core_routers
from app.api.registrars.building import register_building_routers
from app.api.registrars.operations import register_operations_routers
from app.api.registrars.analytics import register_analytics_routers

__all__ = [
    "register_core_routers",
    "register_building_routers",
    "register_operations_routers",
    "register_analytics_routers",
]
