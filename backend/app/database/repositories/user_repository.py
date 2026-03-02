"""
User Repository — Supabase-backed user lookup with JSON fallback.

3-tier fallback: Supabase sentinel_users → JSON users.json → None.
Unknown emails are rejected (no auto-creation).
"""

import json
import logging
from pathlib import Path
from typing import Optional

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_USERS_JSON = _DATA_DIR / "users.json"


class UserRepository:
    """Singleton repository for sentinel_users lookup."""

    _instance: Optional["UserRepository"] = None

    def __new__(cls) -> "UserRepository":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_user_by_email(self, email: str) -> dict | None:
        """Look up a registered user by email.

        Returns dict with keys: user_id, email, full_name, role, is_active.
        Returns None if the email is not registered anywhere.
        """
        email = email.strip().lower()

        # Tier 1: Supabase
        user = self._get_from_supabase(email)
        if user is not None:
            return user

        # Tier 2: JSON fallback
        user = self._get_from_json(email)
        if user is not None:
            return user

        # Not found
        return None

    def list_users(self) -> list[dict]:
        """Return all active users (admin dashboard)."""
        users = self._list_from_supabase()
        if users is not None:
            return users
        return self._list_from_json()

    def create_user(self, email: str, full_name: str, role: str = "auditor") -> dict | None:
        """Create a new user in Supabase. Falls back to JSON append."""
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

        # Fallback: append to JSON
        return self._create_in_json(email, full_name, role)

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

    # ------------------------------------------------------------------
    # Supabase helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    def _get_from_json(self, email: str) -> dict | None:
        users = self._load_json_users()
        for u in users:
            if u.get("email", "").lower() == email and u.get("is_active", True):
                return {
                    "user_id": f"user-{email[:8]}",
                    "email": u["email"],
                    "full_name": u.get("full_name", email.split("@")[0].title()),
                    "role": u.get("role", "auditor"),
                    "is_active": True,
                }
        return None

    def _list_from_json(self) -> list[dict]:
        users = self._load_json_users()
        return [
            {
                "user_id": f"user-{u['email'][:8]}",
                "email": u["email"],
                "full_name": u.get("full_name", ""),
                "role": u.get("role", "auditor"),
                "is_active": u.get("is_active", True),
            }
            for u in users
            if u.get("is_active", True)
        ]

    def _create_in_json(self, email: str, full_name: str, role: str) -> dict | None:
        try:
            users = self._load_json_users()
            new_user = {"email": email, "full_name": full_name, "role": role, "is_active": True}
            users.append(new_user)
            _USERS_JSON.write_text(json.dumps({"users": users}, indent=2))
            return {
                "user_id": f"user-{email[:8]}",
                "email": email,
                "full_name": full_name,
                "role": role,
                "is_active": True,
            }
        except Exception as e:
            logger.error("Failed to create user in JSON fallback: %s", e)
            return None

    def _load_json_users(self) -> list[dict]:
        if not _USERS_JSON.exists():
            return []
        try:
            data = json.loads(_USERS_JSON.read_text())
            return data.get("users", [])
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Row mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: dict) -> dict:
        return {
            "user_id": str(row.get("id", "")),
            "email": row["email"],
            "full_name": row.get("full_name", ""),
            "role": row.get("role", "auditor"),
            "is_active": row.get("is_active", True),
        }


# Singleton accessor
def get_user_repository() -> UserRepository:
    """Return the singleton UserRepository instance."""
    return UserRepository()
