"""Repository for user module grants and access requests."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from app.database.supabase_client import get_supabase_client
from app.models.auth import SentinelRole
from app.models.module_registry import ModuleType
from app.config.demo_configs import has_demo_module_access, has_demo_site_access

import logging

logger = logging.getLogger(__name__)


# Modules included in the default/base package for all authenticated users.
#
# BASE PACKAGE (every user gets these):
# - HVAC: monitor building systems (read-only, no automated control)
# - Energy: energy monitoring and consumption data (read-only)
# - ML: feedback loop, health scoring, risk predictions
# - Notifications: alert notifications
# - Integrations: system health monitoring (SIMBIOT connection status)
#
# All other modules (Control, Solar, Lighting, Assets, etc.) are PAID ADD-ONS
# and require explicit grants via user_module_access table.
BASE_MODULES: set[str] = {
    ModuleType.HVAC.value,  # Base: monitoring only, no automated control
    ModuleType.ENERGY.value,  # Base: energy monitoring, consumption data
    ModuleType.ML.value,  # Base: feedback loop for recommendation improvement
    ModuleType.NOTIFICATIONS.value,  # Base: alert notifications
    ModuleType.INTEGRATIONS.value,  # Base: system health / SIMBIOT connection status
}


class ModuleAccessRepository:
    """Database operations for user module grants and access requests."""

    def __init__(self) -> None:
        self.client = get_supabase_client()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _normalize_modules(module_types: List[str]) -> List[str]:
        normalized: List[str] = []
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
        requested_modules: List[str],
        full_name: Optional[str] = None,
        company: Optional[str] = None,
        phone: Optional[str] = None,
        request_notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
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
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
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

    def get_access_request(self, request_id: str) -> Optional[Dict[str, Any]]:
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
        review_notes: Optional[str] = None,
        granted_modules: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None

        payload: Dict[str, Any] = {
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
        module_types: List[str],
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

    def get_user_modules(self, *, user_email: str, site_code: str) -> List[str]:
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

    def get_effective_modules(
        self,
        *,
        user_email: Optional[str],
        user_role: SentinelRole,
        site_code: str,
    ) -> List[str]:
        if user_role == SentinelRole.ADMIN:
            return [module.value for module in ModuleType]
        effective = set(BASE_MODULES)
        if user_email:
            effective.update(self.get_user_modules(user_email=user_email, site_code=site_code))
        return sorted(effective)

    def has_module_access(
        self,
        *,
        user_email: Optional[str],
        user_role: SentinelRole,
        site_code: str,
        module_type: ModuleType,
    ) -> bool:
        if user_role == SentinelRole.ADMIN:
            return True
        if module_type.value in BASE_MODULES:
            return True
        if not user_email:
            return False

        # Check demo site access first (site-level restriction)
        if not has_demo_site_access(user_email, site_code):
            logger.warning(f"Demo user blocked by site restriction: user={user_email} site={site_code}")
            return False

        # Check demo configs (synced with frontend access-control.ts)
        # This allows demo users to access modules without explicit database grants
        if has_demo_module_access(user_email, module_type.value):
            logger.info(f"Demo config grant: user={user_email} module={module_type.value} site={site_code}")
            return True

        # Fall back to explicit database grants
        return module_type.value in self.get_user_modules(user_email=user_email, site_code=site_code)


def get_module_access_repository() -> ModuleAccessRepository:
    return ModuleAccessRepository()
