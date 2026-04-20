"""
User Site Access Repository - Database operations for user building access control.

ADMIN role always bypasses filtering and sees all buildings.
Other roles see only buildings they've been granted access to.
"""

import logging
from typing import Any

from app.models.auth import SentinelRole

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class UserSiteAccessRepository:
    """Repository for user site access operations."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_accessible_site_ids(self, user_email: str, user_role: SentinelRole) -> list[str]:
        """
        Get list of building UUIDs the user can access.

        ADMIN role bypasses filtering and returns all buildings.

        Args:
            user_email: User's email address (normalized to lowercase)
            user_role: User's role

        Returns:
            List of building UUIDs
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        # ADMIN sees all buildings
        if user_role == SentinelRole.ADMIN:
            try:
                result = self.client.table("sites").select("id").execute()
                return [b["id"] for b in (result.data or [])]
            except Exception as e:
                logger.error(f"Error getting all buildings: {e}")
                return []

        # Other roles see only assigned buildings
        try:
            email = user_email.lower().strip()
            result = self.client.table("user_site_access").select("site_id").eq("user_email", email).execute()

            return [a["site_id"] for a in (result.data or [])]

        except Exception as e:
            logger.error(f"Error getting accessible buildings for {user_email}: {e}")
            return []

    def get_accessible_site_codes(self, user_email: str, user_role: SentinelRole) -> list[str]:
        """
        Get list of building codes the user can access.

        ADMIN role bypasses filtering and returns all buildings.

        Args:
            user_email: User's email address
            user_role: User's role

        Returns:
            List of building codes (e.g., ['site-002', 'site-003'])
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        # ADMIN sees all buildings
        if user_role == SentinelRole.ADMIN:
            try:
                result = self.client.table("sites").select("code").execute()
                return [b["code"] for b in (result.data or [])]
            except Exception as e:
                logger.error(f"Error getting all building codes: {e}")
                return []

        # Other roles see only assigned buildings
        try:
            email = user_email.lower().strip()
            result = (
                self.client.table("user_site_access")
                .select("site_id, buildings(code)")
                .eq("user_email", email)
                .execute()
            )

            codes = []
            for a in result.data or []:
                building = a.get("sites")
                if building and building.get("code"):
                    codes.append(building["code"])
            return codes

        except Exception as e:
            logger.error(f"Error getting accessible building codes for {user_email}: {e}")
            return []

    def has_access_to_site_id(self, user_email: str, user_role: SentinelRole, site_id: str) -> bool:
        """
        Check if user has access to a specific building by UUID.

        Args:
            user_email: User's email address
            user_role: User's role
            site_id: Building UUID

        Returns:
            True if user has access
        """
        if user_role == SentinelRole.ADMIN:
            return True

        if not self.client:
            return False

        try:
            email = user_email.lower().strip()
            result = (
                self.client.table("user_site_access")
                .select("id")
                .eq("user_email", email)
                .eq("site_id", site_id)
                .execute()
            )

            return len(result.data or []) > 0

        except Exception as e:
            logger.error(f"Error checking building access: {e}")
            return False

    def has_access_to_site_code(self, user_email: str, user_role: SentinelRole, site_code: str) -> bool:
        """
        Check if user has access to a specific building by code.

        Args:
            user_email: User's email address
            user_role: User's role
            site_code: Building code (e.g., 'site-002')

        Returns:
            True if user has access
        """
        if user_role == SentinelRole.ADMIN:
            return True

        if not self.client:
            return False

        try:
            # Get building UUID first
            site_result = self.client.table("sites").select("id").eq("code", site_code).execute()

            if not site_result.data:
                return False

            site_id = site_result.data[0]["id"]
            return self.has_access_to_site_id(user_email, user_role, site_id)

        except Exception as e:
            logger.error(f"Error checking building access by code: {e}")
            return False

    def grant_access(self, user_email: str, site_id: str, granted_by: str) -> dict[str, Any] | None:
        """
        Grant a user access to a building.

        Args:
            user_email: User's email address
            site_id: Building UUID
            granted_by: Email or identifier of admin granting access

        Returns:
            Created access record or None on failure
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            email = user_email.lower().strip()
            result = (
                self.client.table("user_site_access")
                .upsert(
                    {
                        "user_email": email,
                        "site_id": site_id,
                        "granted_by": granted_by,
                    },
                    on_conflict="user_email,site_id",
                )
                .execute()
            )

            if result.data:
                logger.info(f"Granted {email} access to building {site_id}")
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error granting access: {e}")
            return None

    def revoke_access(self, user_email: str, site_id: str) -> bool:
        """
        Revoke a user's access to a building.

        Args:
            user_email: User's email address
            site_id: Building UUID

        Returns:
            True if successfully revoked
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return False

        try:
            email = user_email.lower().strip()
            result = (
                self.client.table("user_site_access").delete().eq("user_email", email).eq("site_id", site_id).execute()
            )

            if result.data:
                logger.info(f"Revoked {email} access to building {site_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error revoking access: {e}")
            return False

    def get_user_access_list(self, user_email: str) -> list[dict[str, Any]]:
        """
        Get all building access records for a user.

        Args:
            user_email: User's email address

        Returns:
            List of access records with building details
        """
        if not self.client:
            return []

        try:
            email = user_email.lower().strip()
            result = (
                self.client.table("user_site_access")
                .select("*, buildings(id, code, name, address, region, type)")
                .eq("user_email", email)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting user access list: {e}")
            return []

    def get_building_users(self, site_id: str) -> list[dict[str, Any]]:
        """
        Get all users with access to a building.

        Args:
            site_id: Building UUID

        Returns:
            List of access records
        """
        if not self.client:
            return []

        try:
            result = (
                self.client.table("user_site_access")
                .select("user_email, granted_by, granted_at")
                .eq("site_id", site_id)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting building users: {e}")
            return []

    def grant_default_access(self, user_email: str, granted_by: str = "system") -> bool:
        """
        Grant building access to a new user for ALL registered sites.

        Called when a new user logs in for the first time.
        Queries registered buildings dynamically — no hardcoded site IDs.

        Args:
            user_email: User's email address
            granted_by: Who granted the access (default: 'system')

        Returns:
            True if access was granted to at least one building
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return False

        try:
            from app.core.site_resolver import get_registered_sites

            sites = get_registered_sites()

            if not sites:
                logger.info("No registered buildings — skipping default access grant for %s", user_email)
                return False

            granted_any = False
            for site in sites:
                site_id = site.get("id")
                if not site_id:
                    continue
                result = self.grant_access(user_email, site_id, granted_by)
                if result is not None:
                    granted_any = True

            if granted_any:
                site_codes = [s.get("code", "?") for s in sites]
                logger.info("Granted %s default access to %d building(s): %s", user_email, len(sites), site_codes)

            return granted_any

        except Exception as e:
            logger.error(f"Error granting default access to {user_email}: {e}")
            return False


# Singleton instance
_repository: UserSiteAccessRepository | None = None


def get_user_site_access_repository() -> UserSiteAccessRepository:
    """Get singleton user site access repository."""
    global _repository
    if _repository is None:
        _repository = UserSiteAccessRepository()
    return _repository
