"""Repository for audit log operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from app.database.supabase_client import get_supabase_client


class AuditRepository:
    """Repository for audit log database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get audit log entries with optional filtering.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            user_id: Filter by user ID
            action: Filter by action type
            device_id: Filter by device UUID

        Returns:
            List of audit log entries
        """
        query = (
            self.client.table("audit_log")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
            .range(offset, offset + limit - 1)
        )

        if user_id:
            query = query.eq("user_id", user_id)
        if action:
            query = query.eq("action", action)
        if device_id:
            query = query.eq("device_id", device_id)

        response = query.execute()
        return response.data

    def get_by_id(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get audit log entry by UUID.

        Args:
            entry_id: Entry UUID

        Returns:
            Audit log entry or None if not found
        """
        response = self.client.table("audit_log").select("*").eq("id", entry_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_correlation_id(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Get audit log entries by correlation ID.

        Args:
            correlation_id: Correlation ID

        Returns:
            List of related audit log entries
        """
        response = (
            self.client.table("audit_log")
            .select("*")
            .eq("correlation_id", correlation_id)
            .order("timestamp", desc=True)
            .execute()
        )

        return response.data

    def get_by_device(self, device_uuid: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get audit log entries for a device.

        Args:
            device_uuid: Device UUID
            limit: Maximum number of entries

        Returns:
            List of audit log entries
        """
        response = (
            self.client.table("audit_log")
            .select("*")
            .eq("device_id", device_uuid)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )

        return response.data

    def create(self, audit_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new audit log entry.

        Args:
            audit_data: Audit log data

        Returns:
            Created audit log entry
        """
        # Set timestamp if not provided
        if "timestamp" not in audit_data:
            audit_data["timestamp"] = datetime.now(timezone.utc).isoformat()

        response = self.client.table("audit_log").insert(audit_data).execute()
        return response.data[0]

    def log_device_control(
        self,
        device_id: str,
        point_name: str,
        old_value: Any,
        new_value: Any,
        user_name: str,
        result: str = "SUCCESS",
        safety_validation: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Log a device control action.

        Args:
            device_id: Device UUID
            point_name: Point/device name
            old_value: Old value
            new_value: New value
            user_name: User who performed the action
            result: Result of the action
            safety_validation: Safety validation results
            error_message: Error message if failed
            correlation_id: Correlation ID for related entries
            metadata: Additional metadata

        Returns:
            Created audit log entry
        """
        audit_data = {
            "action": "DEVICE_CONTROL",
            "device_id": device_id,
            "point_name": point_name,
            "old_value": old_value,
            "new_value": new_value,
            "user_name": user_name,
            "result": result,
            "safety_validation": safety_validation,
            "error_message": error_message,
            "correlation_id": correlation_id,
            "metadata": metadata or {},
        }

        return self.create(audit_data)

    def log_safety_validation(
        self,
        device_id: str,
        safety_rules_checked: List[str],
        safety_rules_passed: List[str],
        safety_rules_failed: List[str],
        user_name: str,
        result: str = "SUCCESS",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a safety validation check.

        Args:
            device_id: Device UUID
            safety_rules_checked: List of rules checked
            safety_rules_passed: List of rules that passed
            safety_rules_failed: List of rules that failed
            user_name: User who performed the action
            result: Result of the validation
            correlation_id: Correlation ID for related entries

        Returns:
            Created audit log entry
        """
        audit_data = {
            "action": "SAFETY_VALIDATION",
            "device_id": device_id,
            "user_name": user_name,
            "result": result,
            "safety_rules_checked": safety_rules_checked,
            "safety_rules_passed": safety_rules_passed,
            "safety_rules_failed": safety_rules_failed,
            "correlation_id": correlation_id,
            "metadata": {},
        }

        return self.create(audit_data)

    def get_recent_by_user(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent audit log entries for a user.

        Args:
            user_id: User ID
            limit: Maximum number of entries

        Returns:
            List of recent audit log entries
        """
        return self.get_all(limit=limit, user_id=user_id)

    def get_failed_actions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get failed audit log entries.

        Args:
            limit: Maximum number of entries

        Returns:
            List of failed audit log entries
        """
        response = (
            self.client.table("audit_log")
            .select("*")
            .eq("result", "FAILED")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )

        return response.data

    def log_security_event(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        result: str = "SUCCESS",
    ) -> Dict[str, Any]:
        """Log a security event (Phase 65-04).

        Supported event types:
        - PASSWORD_CHANGE: User password changed
        - PERMISSION_CHANGE: User role/permissions changed
        - API_KEY_CREATED: New API key created
        - API_KEY_REVOKED: API key revoked
        - MFA_ENROLLED: MFA enrollment completed
        - MFA_DISABLED: MFA disabled
        - SESSION_REVOKED: User session manually revoked
        - RATE_LIMIT_EXCEEDED: Rate limit threshold hit
        - LOGIN_SUCCESS: Successful login
        - LOGIN_FAILURE: Failed login attempt
        - LOGOUT: User logout
        - TOKEN_REFRESH: Token refreshed

        Args:
            event_type: Type of security event
            user_id: User ID (optional for some events like rate limit)
            details: Additional event details
            ip_address: Client IP address
            result: Result status (SUCCESS or FAILED)

        Returns:
            Created audit log entry
        """
        audit_data = {
            "action": event_type,
            "user_id": user_id,
            "result": result,
            "details": details or {},
            "ip_address": ip_address,
        }

        return self.create(audit_data)
