"""
MFA Repository - Database operations for MFA secrets and events.

Handles storage and retrieval of TOTP secrets for multi-factor authentication.
FSR Domain: 4.6 - Logical Access Control (MFA for privileged access)
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from ..supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)


class MFARepository:
    """Repository for MFA secrets and event operations."""

    def __init__(self):
        self.client = get_supabase_client()

    # =========================================================================
    # MFA SECRETS OPERATIONS
    # =========================================================================

    def get_mfa_secret(self, user_email: str) -> Optional[Dict[str, Any]]:
        """
        Get MFA secret record for a user.

        Args:
            user_email: User's email address

        Returns:
            MFA secret record or None if not enrolled
        """
        if not self.client:
            logger.warning("Supabase client not available for MFA operations")
            return None

        try:
            result = (
                self.client.table("mfa_secrets")
                .select("*")
                .eq("user_email", user_email.lower().strip())
                .single()
                .execute()
            )

            return result.data
        except Exception as e:
            # Not found is expected for users who haven't enrolled
            if "PGRST116" in str(e):  # No rows returned
                return None
            logger.error(f"Error getting MFA secret for {user_email}: {e}")
            return None

    def create_mfa_secret(
        self,
        user_email: str,
        totp_secret: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Create or update MFA secret for a user.

        Args:
            user_email: User's email address
            totp_secret: Base32-encoded TOTP secret

        Returns:
            Created/updated MFA record or None on failure
        """
        if not self.client:
            logger.warning("Supabase client not available for MFA operations")
            return None

        try:
            email = user_email.lower().strip()

            # Check if record exists
            existing = self.get_mfa_secret(email)

            if existing:
                # Update existing record (re-enrollment)
                result = (
                    self.client.table("mfa_secrets")
                    .update(
                        {
                            "totp_secret": totp_secret,
                            "enabled": False,  # Must verify to enable
                            "failed_attempts": 0,
                            "last_failed_at": None,
                            "created_at": datetime.utcnow().isoformat(),
                        }
                    )
                    .eq("user_email", email)
                    .execute()
                )
            else:
                # Create new record
                result = (
                    self.client.table("mfa_secrets")
                    .insert(
                        {
                            "user_email": email,
                            "totp_secret": totp_secret,
                            "enabled": False,
                            "failed_attempts": 0,
                        }
                    )
                    .execute()
                )

            if result.data:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error creating MFA secret for {user_email}: {e}")
            return None

    def enable_mfa(self, user_email: str) -> bool:
        """
        Enable MFA for a user after successful verification.

        Args:
            user_email: User's email address

        Returns:
            True if enabled successfully
        """
        if not self.client:
            return False

        try:
            result = (
                self.client.table("mfa_secrets")
                .update(
                    {
                        "enabled": True,
                        "last_enrolled_at": datetime.utcnow().isoformat(),
                        "failed_attempts": 0,
                        "last_failed_at": None,
                    }
                )
                .eq("user_email", user_email.lower().strip())
                .execute()
            )

            return bool(result.data)

        except Exception as e:
            logger.error(f"Error enabling MFA for {user_email}: {e}")
            return False

    def disable_mfa(self, user_email: str) -> bool:
        """
        Disable MFA for a user (admin action).

        Args:
            user_email: User's email address

        Returns:
            True if disabled successfully
        """
        if not self.client:
            return False

        try:
            result = self.client.table("mfa_secrets").delete().eq("user_email", user_email.lower().strip()).execute()

            return True  # Delete succeeds even if no record existed

        except Exception as e:
            logger.error(f"Error disabling MFA for {user_email}: {e}")
            return False

    def update_last_used(self, user_email: str) -> bool:
        """
        Update last_used_at timestamp after successful verification.

        Args:
            user_email: User's email address

        Returns:
            True if updated successfully
        """
        if not self.client:
            return False

        try:
            result = (
                self.client.table("mfa_secrets")
                .update(
                    {
                        "last_used_at": datetime.utcnow().isoformat(),
                        "failed_attempts": 0,  # Reset on success
                        "last_failed_at": None,
                    }
                )
                .eq("user_email", user_email.lower().strip())
                .execute()
            )

            return bool(result.data)

        except Exception as e:
            logger.error(f"Error updating last_used for {user_email}: {e}")
            return False

    def record_failed_attempt(self, user_email: str) -> int:
        """
        Record a failed MFA attempt for rate limiting.

        Args:
            user_email: User's email address

        Returns:
            Current failed attempt count
        """
        if not self.client:
            return 0

        try:
            email = user_email.lower().strip()

            # Get current record
            record = self.get_mfa_secret(email)
            if not record:
                return 0

            # Check if we should reset the counter (5 minute window)
            last_failed = record.get("last_failed_at")
            failed_attempts = record.get("failed_attempts", 0)

            if last_failed:
                last_failed_dt = datetime.fromisoformat(last_failed.replace("Z", "+00:00"))
                if datetime.utcnow().replace(tzinfo=last_failed_dt.tzinfo) - last_failed_dt > timedelta(minutes=5):
                    # Reset counter after 5 minutes
                    failed_attempts = 0

            new_count = failed_attempts + 1

            # Update record
            self.client.table("mfa_secrets").update(
                {
                    "failed_attempts": new_count,
                    "last_failed_at": datetime.utcnow().isoformat(),
                }
            ).eq("user_email", email).execute()

            return new_count

        except Exception as e:
            logger.error(f"Error recording failed attempt for {user_email}: {e}")
            return 0

    def is_rate_limited(self, user_email: str, max_attempts: int = 5) -> bool:
        """
        Check if user is rate limited for MFA attempts.

        Args:
            user_email: User's email address
            max_attempts: Maximum attempts allowed in 5-minute window

        Returns:
            True if rate limited
        """
        if not self.client:
            return False

        try:
            record = self.get_mfa_secret(user_email.lower().strip())
            if not record:
                return False

            failed_attempts = record.get("failed_attempts", 0)
            last_failed = record.get("last_failed_at")

            if failed_attempts < max_attempts:
                return False

            if not last_failed:
                return False

            # Check if within 5-minute window
            last_failed_dt = datetime.fromisoformat(last_failed.replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=last_failed_dt.tzinfo)

            return now - last_failed_dt < timedelta(minutes=5)

        except Exception as e:
            logger.error(f"Error checking rate limit for {user_email}: {e}")
            return False

    # =========================================================================
    # MFA EVENTS OPERATIONS
    # =========================================================================

    def log_mfa_event(
        self,
        user_email: str,
        event_type: str,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Log an MFA-related security event.

        Args:
            user_email: User's email address
            event_type: Type of event (mfa_enrolled, mfa_verified, mfa_failed, mfa_disabled, mfa_rate_limited)
            source_ip: Client IP address
            user_agent: Browser/client user agent
            event_data: Additional event metadata

        Returns:
            Created event record or None on failure
        """
        if not self.client:
            logger.warning("Supabase client not available for MFA event logging")
            return None

        try:
            result = (
                self.client.table("mfa_events")
                .insert(
                    {
                        "user_email": user_email.lower().strip(),
                        "event_type": event_type,
                        "source_ip": source_ip,
                        "user_agent": user_agent,
                        "event_data": event_data or {},
                    }
                )
                .execute()
            )

            if result.data:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error logging MFA event for {user_email}: {e}")
            return None

    def get_mfa_events(
        self,
        user_email: Optional[str] = None,
        event_type: Optional[str] = None,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get MFA events with optional filtering.

        Args:
            user_email: Filter by user email
            event_type: Filter by event type
            hours: Only events within the last N hours
            limit: Maximum events to return

        Returns:
            List of MFA event records
        """
        if not self.client:
            return []

        try:
            query = self.client.table("mfa_events").select("*")

            if user_email:
                query = query.eq("user_email", user_email.lower().strip())

            if event_type:
                query = query.eq("event_type", event_type)

            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            query = query.gte("created_at", cutoff)

            query = query.order("created_at", desc=True).limit(limit)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting MFA events: {e}")
            return []

    # =========================================================================
    # MFA BACKUP CODES OPERATIONS
    # =========================================================================

    def replace_backup_codes(
        self,
        user_id: str,
        code_hashes: List[str],
    ) -> bool:
        """Replace all backup codes for a user with a new set."""
        if not self.client:
            return False

        try:
            self.client.table("mfa_backup_codes").delete().eq("user_id", user_id).execute()
            if not code_hashes:
                return True

            payload = [
                {
                    "user_id": user_id,
                    "code_hash": code_hash,
                    "used": False,
                }
                for code_hash in code_hashes
            ]
            result = self.client.table("mfa_backup_codes").insert(payload).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error replacing MFA backup codes for {user_id}: {e}")
            return False

    def get_backup_codes(
        self,
        user_id: str,
        include_used: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get backup code rows for a user."""
        if not self.client:
            return []

        try:
            query = self.client.table("mfa_backup_codes").select("*").eq("user_id", user_id)
            if not include_used:
                query = query.eq("used", False)
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting MFA backup codes for {user_id}: {e}")
            return []

    def mark_backup_code_used(self, code_id: str) -> bool:
        """Mark a backup code row as used."""
        if not self.client:
            return False

        try:
            result = (
                self.client.table("mfa_backup_codes")
                .update(
                    {
                        "used": True,
                        "used_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", code_id)
                .eq("used", False)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error marking MFA backup code as used ({code_id}): {e}")
            return False

    def count_unused_backup_codes(self, user_id: str) -> int:
        """Count remaining unused backup codes for a user."""
        if not self.client:
            return 0

        try:
            result = (
                self.client.table("mfa_backup_codes")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("used", False)
                .execute()
            )
            return int(result.count or 0)
        except Exception as e:
            logger.error(f"Error counting MFA backup codes for {user_id}: {e}")
            return 0


# Singleton instance
_repository: Optional[MFARepository] = None


def get_mfa_repository() -> MFARepository:
    """Get singleton MFA repository."""
    global _repository
    if _repository is None:
        _repository = MFARepository()
    return _repository
