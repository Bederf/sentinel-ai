"""
User Site Access Repository - Database operations for user building access control.

ADMIN role always bypasses filtering and sees all buildings.
Other roles see only buildings they've been granted access to.
"""

from typing import Optional, List, Dict, Any
from ..supabase_client import get_supabase_client
from app.models.auth import SentinelRole
import logging

logger = logging.getLogger(__name__)


class UserSiteAccessRepository:
    """Repository for user site access operations."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_accessible_building_ids(
        self, user_email: str, user_role: SentinelRole
    ) -> List[str]:
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
                result = self.client.table("buildings").select("id").execute()
                return [b["id"] for b in (result.data or [])]
            except Exception as e:
                logger.error(f"Error getting all buildings: {e}")
                return []

        # Other roles see only assigned buildings
        try:
            email = user_email.lower().strip()
            result = self.client.table("user_site_access").select(
                "building_id"
            ).eq("user_email", email).execute()

            return [a["building_id"] for a in (result.data or [])]

        except Exception as e:
            logger.error(f"Error getting accessible buildings for {user_email}: {e}")
            return []

    def get_accessible_building_codes(
        self, user_email: str, user_role: SentinelRole
    ) -> List[str]:
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
                result = self.client.table("buildings").select("code").execute()
                return [b["code"] for b in (result.data or [])]
            except Exception as e:
                logger.error(f"Error getting all building codes: {e}")
                return []

        # Other roles see only assigned buildings
        try:
            email = user_email.lower().strip()
            result = self.client.table("user_site_access").select(
                "building_id, buildings(code)"
            ).eq("user_email", email).execute()

            codes = []
            for a in (result.data or []):
                building = a.get("buildings")
                if building and building.get("code"):
                    codes.append(building["code"])
            return codes

        except Exception as e:
            logger.error(f"Error getting accessible building codes for {user_email}: {e}")
            return []

    def has_access_to_building_id(
        self, user_email: str, user_role: SentinelRole, building_id: str
    ) -> bool:
        """
        Check if user has access to a specific building by UUID.

        Args:
            user_email: User's email address
            user_role: User's role
            building_id: Building UUID

        Returns:
            True if user has access
        """
        if user_role == SentinelRole.ADMIN:
            return True

        if not self.client:
            return False

        try:
            email = user_email.lower().strip()
            result = self.client.table("user_site_access").select(
                "id"
            ).eq("user_email", email).eq("building_id", building_id).execute()

            return len(result.data or []) > 0

        except Exception as e:
            logger.error(f"Error checking building access: {e}")
            return False

    def has_access_to_building_code(
        self, user_email: str, user_role: SentinelRole, building_code: str
    ) -> bool:
        """
        Check if user has access to a specific building by code.

        Args:
            user_email: User's email address
            user_role: User's role
            building_code: Building code (e.g., 'site-002')

        Returns:
            True if user has access
        """
        if user_role == SentinelRole.ADMIN:
            return True

        if not self.client:
            return False

        try:
            # Get building UUID first
            building_result = self.client.table("buildings").select(
                "id"
            ).eq("code", building_code).execute()

            if not building_result.data:
                return False

            building_id = building_result.data[0]["id"]
            return self.has_access_to_building_id(user_email, user_role, building_id)

        except Exception as e:
            logger.error(f"Error checking building access by code: {e}")
            return False

    def grant_access(
        self, user_email: str, building_id: str, granted_by: str
    ) -> Optional[Dict[str, Any]]:
        """
        Grant a user access to a building.

        Args:
            user_email: User's email address
            building_id: Building UUID
            granted_by: Email or identifier of admin granting access

        Returns:
            Created access record or None on failure
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            email = user_email.lower().strip()
            result = self.client.table("user_site_access").upsert({
                "user_email": email,
                "building_id": building_id,
                "granted_by": granted_by,
            }, on_conflict="user_email,building_id").execute()

            if result.data:
                logger.info(f"Granted {email} access to building {building_id}")
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error granting access: {e}")
            return None

    def revoke_access(self, user_email: str, building_id: str) -> bool:
        """
        Revoke a user's access to a building.

        Args:
            user_email: User's email address
            building_id: Building UUID

        Returns:
            True if successfully revoked
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return False

        try:
            email = user_email.lower().strip()
            result = self.client.table("user_site_access").delete().eq(
                "user_email", email
            ).eq("building_id", building_id).execute()

            if result.data:
                logger.info(f"Revoked {email} access to building {building_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error revoking access: {e}")
            return False

    def get_user_access_list(self, user_email: str) -> List[Dict[str, Any]]:
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
            result = self.client.table("user_site_access").select(
                "*, buildings(id, code, name, address, region, type)"
            ).eq("user_email", email).execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting user access list: {e}")
            return []

    def get_building_users(self, building_id: str) -> List[Dict[str, Any]]:
        """
        Get all users with access to a building.

        Args:
            building_id: Building UUID

        Returns:
            List of access records
        """
        if not self.client:
            return []

        try:
            result = self.client.table("user_site_access").select(
                "user_email, granted_by, granted_at"
            ).eq("building_id", building_id).execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting building users: {e}")
            return []

    def grant_default_access(self, user_email: str, granted_by: str = "system") -> bool:
        """
        Grant default building access to a new user (site-002 Sandton City).

        Called when a new user logs in for the first time.

        Args:
            user_email: User's email address
            granted_by: Who granted the access (default: 'system')

        Returns:
            True if access was granted
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return False

        try:
            # Get default building (site-002)
            building_result = self.client.table("buildings").select(
                "id"
            ).eq("code", "site-002").execute()

            if not building_result.data:
                logger.warning("Default building site-002 not found")
                return False

            building_id = building_result.data[0]["id"]

            # Grant access
            result = self.grant_access(user_email, building_id, granted_by)
            return result is not None

        except Exception as e:
            logger.error(f"Error granting default access to {user_email}: {e}")
            return False


# Singleton instance
_repository: Optional[UserSiteAccessRepository] = None


def get_user_site_access_repository() -> UserSiteAccessRepository:
    """Get singleton user site access repository."""
    global _repository
    if _repository is None:
        _repository = UserSiteAccessRepository()
    return _repository
