"""Repository for user module grants and access requests."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.config.access_profiles import has_profile_module_access, has_profile_site_access
from app.database.supabase_client import get_supabase_client
from app.models.auth import SentinelRole
from app.models.module_registry import ModuleType
from app.services.module_registry_service import module_registry

logger = logging.getLogger(__name__)


class ModuleAccessRepository:
    """Database operations for user module grants and access requests."""

    def __init__(self) -> None:
        self.client = get_supabase_client()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _normalize_modules(module_types: list[str]) -> list[str]:
        normalized: list[str] = []
        for module_type in module_types:
            candidate = module_type.strip().lower()
            if not candidate:
                continue
            try:
                normalized.append(ModuleType(candidate).value)
            except ValueError:
                logger.warning("Ignoring invalid module type in grant/request: %s", module_type)
        # preserve order while deduplicating
        return list(dict.fromkeys(normalized))

    def submit_access_request(
        self,
        *,
        user_email: str,
        site_code: str,
        requested_modules: list[str],
        full_name: str | None = None,
        company: str | None = None,
        phone: str | None = None,
        request_notes: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.client:
            return None

        email = self._normalize_email(user_email)
        modules = self._normalize_modules(requested_modules)
        payload = {
            "user_email": email,
            "site_code": site_code,
            "requested_modules": modules,
            "full_name": full_name,
            "company": company,
            "phone": phone,
            "request_notes": request_notes,
            "status": "pending",
        }

        try:
            # Single pending request per user/site. Update payload if it already exists.
            existing = (
                self.client.table("access_requests")
                .select("id")
                .eq("user_email", email)
                .eq("site_code", site_code)
                .eq("status", "pending")
                .limit(1)
                .execute()
            )
            if existing.data:
                request_id = existing.data[0]["id"]
                result = self.client.table("access_requests").update(payload).eq("id", request_id).execute()
                return (result.data or [None])[0]

            result = self.client.table("access_requests").insert(payload).execute()
            return (result.data or [None])[0]
        except Exception as exc:
            logger.error("Failed submitting access request for %s: %s", email, exc)
            return None

    def list_access_requests(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            query = self.client.table("access_requests").select("*").order("created_at", desc=True).limit(limit)
            if status:
                query = query.eq("status", status)
            result = query.execute()
            return result.data or []
        except Exception as exc:
            logger.error("Failed listing access requests: %s", exc)
            return []

    def get_access_request(self, request_id: str) -> dict[str, Any] | None:
        if not self.client:
            return None
        try:
            result = self.client.table("access_requests").select("*").eq("id", request_id).limit(1).execute()
            return (result.data or [None])[0]
        except Exception as exc:
            logger.error("Failed fetching access request %s: %s", request_id, exc)
            return None

    def set_access_request_decision(
        self,
        *,
        request_id: str,
        status: str,
        reviewed_by: str,
        review_notes: str | None = None,
        granted_modules: list[str] | None = None,
    ) -> dict[str, Any] | None:
        if not self.client:
            return None

        payload: dict[str, Any] = {
            "status": status,
            "reviewed_by": reviewed_by,
            "review_notes": review_notes,
            "reviewed_at": datetime.utcnow().isoformat(),
        }
        if granted_modules is not None:
            payload["granted_modules"] = self._normalize_modules(granted_modules)

        try:
            result = self.client.table("access_requests").update(payload).eq("id", request_id).execute()
            return (result.data or [None])[0]
        except Exception as exc:
            logger.error("Failed updating access request %s: %s", request_id, exc)
            return None

    def set_user_modules(
        self,
        *,
        user_email: str,
        site_code: str,
        module_types: list[str],
        granted_by: str,
        replace_existing: bool = True,
    ) -> bool:
        if not self.client:
            return False

        email = self._normalize_email(user_email)
        modules = self._normalize_modules(module_types)

        try:
            if replace_existing:
                self.client.table("user_module_access").delete().eq("user_email", email).eq(
                    "site_code", site_code
                ).execute()

            if not modules:
                return True

            rows = [
                {
                    "user_email": email,
                    "site_code": site_code,
                    "module_type": module_type,
                    "granted_by": granted_by,
                }
                for module_type in modules
            ]
            self.client.table("user_module_access").upsert(
                rows,
                on_conflict="user_email,site_code,module_type",
            ).execute()
            return True
        except Exception as exc:
            logger.error(
                "Failed setting module grants for %s @ %s: %s",
                email,
                site_code,
                exc,
            )
            return False

    def get_user_modules(self, *, user_email: str, site_code: str) -> list[str]:
        if not self.client:
            return []

        email = self._normalize_email(user_email)
        try:
            result = (
                self.client.table("user_module_access")
                .select("module_type")
                .eq("user_email", email)
                .eq("site_code", site_code)
                .execute()
            )
            return [row["module_type"] for row in (result.data or []) if row.get("module_type")]
        except Exception as exc:
            logger.error("Failed getting user modules for %s @ %s: %s", email, site_code, exc)
            return []

    def get_active_modules(self, *, site_code: str) -> list[str]:
        """Return enabled site modules with mandatory registry modules always included."""
        registry = module_registry.get_module_registry()
        enabled_modules = {module_type.value for module_type, definition in registry.items() if definition.enabled}
        mandatory_modules = {
            module_type.value
            for module_type, definition in registry.items()
            if definition.enabled and definition.mandatory
        }
        site_active_modules = {
            module.module_type.value
            for module in module_registry.get_active_modules(site_code)
            if module.module_type.value in enabled_modules
        }
        return sorted(mandatory_modules | site_active_modules)

    def get_effective_modules(
        self,
        *,
        user_email: str | None,
        user_role: SentinelRole,
        site_code: str,
    ) -> list[str]:
        if user_role == SentinelRole.ADMIN:
            return self.get_active_modules(site_code=site_code)

        active_modules = set(self.get_active_modules(site_code=site_code))
        registry = module_registry.get_module_registry()
        effective = {
            module_type
            for module_type in active_modules
            if (definition := registry.get(ModuleType(module_type))) and definition.mandatory
        }
        if user_email:
            profile_modules = {
                module.value
                for module in ModuleType
                if module.value in active_modules and has_profile_module_access(user_email, module.value)
            }
            explicit_modules = set(self.get_user_modules(user_email=user_email, site_code=site_code))
            effective.update(profile_modules)
            effective.update(explicit_modules & active_modules)
        return sorted(effective)

    def has_module_access(
        self,
        *,
        user_email: str | None,
        user_role: SentinelRole,
        site_code: str,
        module_type: ModuleType,
    ) -> bool:
        if user_role == SentinelRole.ADMIN:
            return module_type.value in set(self.get_active_modules(site_code=site_code))

        active_modules = set(self.get_active_modules(site_code=site_code))
        if module_type.value not in active_modules:
            return False

        definition = module_registry.get_module_registry().get(module_type)
        if definition and definition.mandatory:
            return True
        if not user_email:
            return False

        # Check profiled site access first (site-level restriction)
        if not has_profile_site_access(user_email, site_code):
            logger.warning(f"Demo user blocked by site restriction: user={user_email} site={site_code}")
            return False

        # Check access profiles (synced with frontend access-control.ts)
        # This allows profiled users to access modules without explicit database grants
        if has_profile_module_access(user_email, module_type.value):
            logger.info(f"Demo config grant: user={user_email} module={module_type.value} site={site_code}")
            return True

        # Fall back to explicit database grants
        return module_type.value in self.get_user_modules(user_email=user_email, site_code=site_code)


def get_module_access_repository() -> ModuleAccessRepository:
    return ModuleAccessRepository()
