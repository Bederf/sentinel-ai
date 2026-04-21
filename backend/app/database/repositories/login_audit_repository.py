"""
Login Audit Repository - Database operations for login audit logging.

Tracks all login attempts for security auditing and compliance.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class LoginAuditRepository:
    """Repository for login audit operations."""

    def __init__(self):
        self.client = get_supabase_client()

    def log_login(
        self,
        user_email: str,
        user_id: str,
        user_role: str,
        source_ip: str,
        user_agent: str | None = None,
        is_new_user: bool = False,
        success: bool = True,
        failure_reason: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Log a login attempt.

        Args:
            user_email: User's email address
            user_id: User's ID
            user_role: User's role
            source_ip: Client IP address
            user_agent: Browser/client user agent
            is_new_user: Whether this is a new user's first login
            success: Whether login was successful
            failure_reason: Reason for failure if not successful

        Returns:
            Created audit record or None on failure
        """
        if not self.client:
            logger.warning("Supabase client not available for login audit")
            return None

        try:
            result = (
                self.client.table("login_audit")
                .insert(
                    {
                        "user_email": user_email.lower().strip(),
                        "user_id": user_id,
                        "user_role": user_role,
                        "source_ip": source_ip,
                        "user_agent": user_agent,
                        "is_new_user": is_new_user,
                        "success": success,
                        "failure_reason": failure_reason,
                    }
                )
                .execute()
            )

            if result.data:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error logging login audit: {e}")
            return None

    def get_recent_logins(
        self,
        limit: int = 100,
        user_email: str | None = None,
        source_ip: str | None = None,
        success_only: bool | None = None,
        hours: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get recent login records with optional filtering.

        Args:
            limit: Maximum records to return (default 100)
            user_email: Filter by user email
            source_ip: Filter by source IP
            success_only: If True, only successful logins; if False, only failures
            hours: Only logins within the last N hours

        Returns:
            List of login audit records
        """
        if not self.client:
            return []

        try:
            query = self.client.table("login_audit").select("*")

            if user_email:
                query = query.eq("user_email", user_email.lower().strip())

            if source_ip:
                query = query.eq("source_ip", source_ip)

            if success_only is not None:
                query = query.eq("success", success_only)

            if hours:
                cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
                query = query.gte("login_at", cutoff)

            query = query.order("login_at", desc=True).limit(limit)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting login audit: {e}")
            return []

    def get_login_stats(self, hours: int = 24) -> dict[str, Any]:
        """
        Get login statistics for the specified time period.

        Args:
            hours: Time period in hours (default 24)

        Returns:
            Statistics dict with counts and breakdowns
        """
        if not self.client:
            return {"total": 0, "successful": 0, "failed": 0, "new_users": 0, "unique_users": 0}

        try:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

            # Get all logins in period
            result = (
                self.client.table("login_audit")
                .select("user_email, success, is_new_user")
                .gte("login_at", cutoff)
                .execute()
            )

            records = result.data or []

            total = len(records)
            successful = len([r for r in records if r.get("success")])
            failed = total - successful
            new_users = len([r for r in records if r.get("is_new_user")])
            unique_users = len({r.get("user_email") for r in records})

            return {
                "period_hours": hours,
                "total": total,
                "successful": successful,
                "failed": failed,
                "new_users": new_users,
                "unique_users": unique_users,
            }

        except Exception as e:
            logger.error(f"Error getting login stats: {e}")
            return {"total": 0, "successful": 0, "failed": 0, "new_users": 0, "unique_users": 0}

    def get_user_login_history(self, user_email: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get login history for a specific user.

        Args:
            user_email: User's email address
            limit: Maximum records to return

        Returns:
            List of login records for the user
        """
        return self.get_recent_logins(limit=limit, user_email=user_email)

    def get_suspicious_activity(self, hours: int = 24) -> dict[str, Any]:
        """
        Detect potentially suspicious login activity.

        Looks for:
        - Multiple failed logins from same IP
        - Logins from many different IPs for same user
        - High volume of new user registrations

        Args:
            hours: Time period to analyze

        Returns:
            Dict with suspicious activity indicators
        """
        if not self.client:
            return {"failed_ips": [], "multi_ip_users": [], "new_user_surge": False}

        try:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

            result = (
                self.client.table("login_audit")
                .select("user_email, source_ip, success, is_new_user")
                .gte("login_at", cutoff)
                .execute()
            )

            records = result.data or []

            # Count failed logins by IP
            failed_by_ip: dict[str, int] = {}
            for r in records:
                if not r.get("success"):
                    ip = r.get("source_ip", "unknown")
                    failed_by_ip[ip] = failed_by_ip.get(ip, 0) + 1

            # IPs with 5+ failures
            failed_ips = [{"ip": ip, "count": count} for ip, count in failed_by_ip.items() if count >= 5]

            # Users logging in from many IPs
            user_ips: dict[str, set] = {}
            for r in records:
                email = r.get("user_email", "")
                ip = r.get("source_ip", "")
                if email not in user_ips:
                    user_ips[email] = set()
                user_ips[email].add(ip)

            # Users with 5+ different IPs
            multi_ip_users = [
                {"email": email, "ip_count": len(ips)} for email, ips in user_ips.items() if len(ips) >= 5
            ]

            # New user surge (more than 10 new users in period)
            new_users = len([r for r in records if r.get("is_new_user")])
            new_user_surge = new_users > 10

            return {
                "period_hours": hours,
                "failed_ips": failed_ips,
                "multi_ip_users": multi_ip_users,
                "new_user_surge": new_user_surge,
                "new_user_count": new_users,
            }

        except Exception as e:
            logger.error(f"Error detecting suspicious activity: {e}")
            return {"failed_ips": [], "multi_ip_users": [], "new_user_surge": False}


# Singleton instance
_repository: LoginAuditRepository | None = None


def get_login_audit_repository() -> LoginAuditRepository:
    """Get singleton login audit repository."""
    global _repository
    if _repository is None:
        _repository = LoginAuditRepository()
    return _repository
