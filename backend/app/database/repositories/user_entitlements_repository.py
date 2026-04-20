"""User entitlements repository backed by the canonical DB store."""

import logging

from app.database.supabase_client import get_supabase_client
from app.models.user_entitlements import PRESET_ENTITLEMENTS, UserEntitlementProfile

logger = logging.getLogger(__name__)


class UserEntitlementsRepository:
    """Repository for user module entitlements."""

    async def get_user_entitlements(self, user_email: str) -> UserEntitlementProfile | None:
        """Get module entitlements for a user from the canonical DB store."""
        try:
            client = get_supabase_client()
            response = (
                client.table("user_entitlements")
                .select("user_id, user_email, modules, updated_at")
                .eq("user_email", user_email)
                .single()
                .execute()
            )

            if response.data:
                return UserEntitlementProfile(
                    user_id=response.data.get("user_id", user_email),
                    user_email=response.data.get("user_email", user_email),
                    entitlements=response.data.get("modules", []),
                    last_updated=response.data.get("updated_at", ""),
                )
        except Exception as e:
            logger.error("Canonical entitlements query failed for %s: %s", user_email, e)

        logger.debug("No entitlements found for user %s", user_email)
        return None

    async def set_user_entitlements(
        self, user_email: str, modules: list[str], user_id: str | None = None
    ) -> UserEntitlementProfile:
        """Set/update module entitlements for a user in the canonical DB store."""
        user_id = user_id or user_email
        client = get_supabase_client()
        client.table("user_entitlements").upsert(
            {"user_id": user_id, "user_email": user_email, "modules": modules}
        ).execute()
        logger.info("Updated entitlements in canonical DB for %s: %s", user_email, modules)
        return UserEntitlementProfile(user_id=user_id, user_email=user_email, entitlements=modules, last_updated="")

    async def apply_preset_to_user(
        self, user_email: str, preset_name: str, user_id: str | None = None
    ) -> UserEntitlementProfile | None:
        """Apply a preset (grant, bederf, full) to a user."""
        if preset_name not in PRESET_ENTITLEMENTS:
            logger.error("Unknown preset: %s", preset_name)
            return None

        modules = PRESET_ENTITLEMENTS[preset_name]["modules"]
        return await self.set_user_entitlements(user_email, modules, user_id)


def get_user_entitlements_repository() -> UserEntitlementsRepository:
    """Get singleton instance of user entitlements repository."""
    return UserEntitlementsRepository()
