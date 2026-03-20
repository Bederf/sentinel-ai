"""User Repository — canonical user lookup from sentinel_users."""

import logging
from typing import Optional

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class UserRepository:
    """Singleton repository for sentinel_users lookup."""

    _instance: Optional["UserRepository"] = None

    def __new__(cls) -> "UserRepository":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_user_by_email(self, email: str) -> dict | None:
        """Look up a registered user by email in the canonical DB store."""
        email = email.strip().lower()
        return self._get_from_supabase(email)

    def list_users(self) -> list[dict]:
        """Return all active users from the canonical DB store."""
        users = self._list_from_supabase()
        return users or []

    def create_user(self, email: str, full_name: str, role: str = "auditor") -> dict | None:
        """Create a new user in the canonical DB store."""
        email = email.strip().lower()
        client = get_supabase_client()
        if client:
            try:
                result = (
                    client.table("sentinel_users")
                    .insert({"email": email, "full_name": full_name, "role": role})
                    .execute()
                )
                if result.data:
                    row = result.data[0]
                    return self._row_to_dict(row)
            except Exception as e:
                logger.error("Failed to create user in Supabase: %s", e)
        return None

    def ensure_admin_emails(self, admin_emails: list[str]) -> None:
        """Bootstrap ADMIN_EMAILS env var users — create if missing, upgrade if exists."""
        for raw_email in admin_emails:
            email = raw_email.strip().lower()
            if not email:
                continue
            existing = self.get_user_by_email(email)
            if existing is None:
                self.create_user(email, "Admin User", "admin")
                logger.info("Bootstrapped admin user: %s", email)
            elif existing.get("role") != "admin":
                self._set_role_supabase(email, "admin")
                logger.info("Upgraded user %s to admin (ADMIN_EMAILS)", email)

    def _get_from_supabase(self, email: str) -> dict | None:
        client = get_supabase_client()
        if not client:
            return None
        try:
            result = (
                client.table("sentinel_users").select("*").eq("email", email).eq("is_active", True).limit(1).execute()
            )
            if result.data:
                return self._row_to_dict(result.data[0])
        except Exception as e:
            logger.warning("Supabase user lookup failed for %s: %s", email, e)
        return None

    def _list_from_supabase(self) -> list[dict] | None:
        client = get_supabase_client()
        if not client:
            return None
        try:
            result = client.table("sentinel_users").select("*").eq("is_active", True).execute()
            return [self._row_to_dict(r) for r in (result.data or [])]
        except Exception as e:
            logger.warning("Supabase user list failed: %s", e)
            return None

    def _set_role_supabase(self, email: str, role: str) -> None:
        client = get_supabase_client()
        if not client:
            return
        try:
            client.table("sentinel_users").update({"role": role}).eq("email", email).execute()
        except Exception as e:
            logger.warning("Failed to update role in Supabase for %s: %s", email, e)

    @staticmethod
    def _row_to_dict(row: dict) -> dict:
        return {
            "user_id": str(row.get("id", "")),
            "email": row["email"],
            "full_name": row.get("full_name", ""),
            "role": row.get("role", "auditor"),
            "is_active": row.get("is_active", True),
        }


def get_user_repository() -> UserRepository:
    """Return the singleton UserRepository instance."""
    return UserRepository()
