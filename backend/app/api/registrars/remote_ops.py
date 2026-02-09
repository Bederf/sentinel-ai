"""Remote operations API router registrar.

Registers routers for remote operations, dispatch, and monitoring.
"""

from fastapi import FastAPI

from app.api import remote_ops, remote_commands, dispatch


def register_remote_ops_routers(app: FastAPI) -> None:
    """Register remote operations API routers."""
    # Remote operations monitoring
    app.include_router(remote_ops.router, tags=["remote-ops"])

    # Remote command execution
    app.include_router(remote_commands.router, prefix="/api/remote", tags=["remote-ops"])

    # Smart dispatch & task bundling
    app.include_router(dispatch.router, prefix="/api/dispatch", tags=["dispatch"])
