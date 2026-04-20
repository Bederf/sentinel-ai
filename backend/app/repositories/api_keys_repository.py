"""API Keys Repository for Supabase-backed API key management.

Phase 168-01: Replaces in-memory API key store with persistent, auditable storage.
Provides query methods for validating API keys, checking expiration, and rotation support.

Note: Uses synchronous Supabase client calls to match existing middleware patterns.
"""

import hashlib
import logging
from datetime import datetime

from app.database.supabase_client import get_supabase_client
from app.models.auth import SentinelRole

_logger = logging.getLogger(__name__)

# Role ID mappings (must match role values in sentinel_users table)
ROLE_ID_MAP = {
    SentinelRole.ADMIN: 5,
    SentinelRole.DEVELOPER: 4,
    SentinelRole.OPERATOR: 3,
    SentinelRole.AUDITOR: 2,
    SentinelRole.BOT_AGENT: 1,
}


class APIKeysRepository:
    """Repository for managing API keys in Supabase."""

    def __init__(self):
        """Initialize with Supabase client."""
        self.client = get_supabase_client()

    def validate_api_key(self, key: str) -> dict | None:
        """Validate an API key against the database.

        Checks:
        1. Key hash exists in api_keys table
        2. Key is active
        3. Key has not expired
        4. Returns role information

        Args:
            key: Raw API key string

        Returns:
            Dict with 'owner_role' and 'api_key_id' if valid, None otherwise
        """
        try:
            key_hash = hashlib.sha256(key.encode()).hexdigest()

            # Query Supabase for matching key
            result = (
                self.client.table("api_keys")
                .select("id", "owner_role", "expires_at")
                .eq("key_hash", key_hash)
                .eq("active", True)
                .single()
                .execute()
            )

            if not result.data:
                _logger.debug("API key validation failed: key not found")
                return None

            api_key = result.data

            # Check expiration
            if api_key.get("expires_at"):
                expires_at = datetime.fromisoformat(api_key["expires_at"].replace("Z", "+00:00"))
                if datetime.now(expires_at.tzinfo) > expires_at:
                    _logger.debug("API key validation failed: key expired")
                    return None

            return {
                "api_key_id": api_key["id"],
                "owner_role": api_key["owner_role"],
            }

        except Exception as e:
            _logger.debug(f"API key validation error: {e}")
            return None

    def get_api_key_metadata(self, api_key_id: str) -> dict | None:
        """Retrieve metadata for an API key.

        Args:
            api_key_id: UUID of the API key

        Returns:
            Dict with key metadata or None if not found
        """
        try:
            result = (
                self.client.table("api_keys")
                .select("id", "display_name", "owner_role", "active", "created_at", "expires_at", "last_rotated_at")
                .eq("id", api_key_id)
                .single()
                .execute()
            )

            return result.data if result.data else None

        except Exception as e:
            _logger.debug(f"Error retrieving API key metadata: {e}")
            return None

    def create_api_key(
        self,
        key_hash: str,
        display_name: str,
        owner_role: SentinelRole,
        created_by: str,
        expires_at: datetime | None = None,
    ) -> dict | None:
        """Create a new API key in the database.

        Args:
            key_hash: SHA-256 hash of the API key
            display_name: Human-readable name for the key
            owner_role: SentinelRole assigned to this key
            created_by: UUID of the user creating the key
            expires_at: Optional expiration timestamp

        Returns:
            Dict with created key ID or None on error
        """
        try:
            owner_role_id = ROLE_ID_MAP.get(owner_role, ROLE_ID_MAP[SentinelRole.AUDITOR])

            result = (
                self.client.table("api_keys")
                .insert(
                    {
                        "key_hash": key_hash,
                        "display_name": display_name,
                        "owner_role": owner_role_id,
                        "created_by": created_by,
                        "expires_at": expires_at.isoformat() if expires_at else None,
                        "active": True,
                    }
                )
                .execute()
            )

            if result.data and len(result.data) > 0:
                _logger.info(f"API key created: {display_name}")
                return result.data[0]

            return None

        except Exception as e:
            _logger.error(f"Error creating API key: {e}")
            return None

    def rotate_api_key(self, api_key_id: str, new_key_hash: str) -> bool:
        """Rotate an API key by updating its hash and last_rotated_at timestamp.

        Args:
            api_key_id: UUID of the API key to rotate
            new_key_hash: SHA-256 hash of the new key

        Returns:
            True if successful, False otherwise
        """
        try:
            result = (
                self.client.table("api_keys")
                .update(
                    {
                        "key_hash": new_key_hash,
                        "last_rotated_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", api_key_id)
                .execute()
            )

            if result.data:
                _logger.info(f"API key rotated: {api_key_id}")
                return True

            return False

        except Exception as e:
            _logger.error(f"Error rotating API key: {e}")
            return False

    def deactivate_api_key(self, api_key_id: str) -> bool:
        """Deactivate an API key without deleting it (audit trail).

        Args:
            api_key_id: UUID of the API key to deactivate

        Returns:
            True if successful, False otherwise
        """
        try:
            result = (
                self.client.table("api_keys")
                .update(
                    {
                        "active": False,
                    }
                )
                .eq("id", api_key_id)
                .execute()
            )

            if result.data:
                _logger.info(f"API key deactivated: {api_key_id}")
                return True

            return False

        except Exception as e:
            _logger.error(f"Error deactivating API key: {e}")
            return False


# Singleton instance
_api_keys_repository: APIKeysRepository | None = None


def get_api_keys_repository() -> APIKeysRepository:
    """Get the singleton API keys repository instance.

    Returns:
        APIKeysRepository instance
    """
    global _api_keys_repository
    if _api_keys_repository is None:
        _api_keys_repository = APIKeysRepository()
    return _api_keys_repository
