"""Module access dependencies for API route protection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Callable, Awaitable

from fastapi import HTTPException, Request

from app.database.repositories.module_access_repository import get_module_access_repository
from app.models.auth import SentinelRole
from app.models.module_registry import ModuleType
from app.services.module_registry_service import module_registry


def require_active_module(
    module_type: ModuleType,
    *,
    site_keys: Sequence[str] = ("site_id", "site"),
    default_site_id: str | None = None,
) -> Callable[[Request], Awaitable[None]]:
    """Build a dependency that blocks access when a module is inactive.

    Notes:
    - Site is resolved from path params, query params, then `X-Site-Id` header.
    - If no site can be resolved, dependency is fail-open to avoid breaking
      non-site-scoped endpoints.
    """

    async def _dependency(request: Request) -> None:
        site_id: str | None = None

        for key in site_keys:
            path_value = request.path_params.get(key)
            if isinstance(path_value, str) and path_value.strip():
                site_id = path_value.strip()
                break

            query_value = request.query_params.get(key)
            if isinstance(query_value, str) and query_value.strip():
                site_id = query_value.strip()
                break

        if not site_id:
            header_value = request.headers.get("x-site-id")
            if header_value and header_value.strip():
                site_id = header_value.strip()

        if not site_id and default_site_id:
            site_id = default_site_id

        if not site_id:
            return

        if not module_registry.is_module_active(site_id, module_type):
            raise HTTPException(
                status_code=403,
                detail=f"Module '{module_type.value}' is not active for site '{site_id}'",
            )

        # Per-user module grants (admins bypass).
        auth_ctx = getattr(request.state, "auth", None)
        if auth_ctx and getattr(auth_ctx, "role", None) != SentinelRole.ADMIN:
            repo = get_module_access_repository()
            if not repo.has_module_access(
                user_email=getattr(auth_ctx, "email", None),
                user_role=getattr(auth_ctx, "role", SentinelRole.AUDITOR),
                site_code=site_id,
                module_type=module_type,
            ):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"User '{getattr(auth_ctx, 'email', 'unknown')}' is not granted "
                        f"module '{module_type.value}' for site '{site_id}'"
                    ),
                )

    return _dependency
