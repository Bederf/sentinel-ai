"""Audit Logger Service.

Thread-safe audit logging service for recording all control actions,
safety validations, and system events. Uses JSON file storage for demo
with in-memory buffer and periodic flush.

Enhanced (Phase 63): Adds structured JSON logging output alongside
file-based logging. Structured logs are collected by Promtail and
shipped to Loki for centralised aggregation and SIEM alerting.
"""

import json
import logging
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from app.models.audit_log import AuditLogEntry, AuditActionType, AuditResultType

logger = logging.getLogger(__name__)

# Structured audit logger for Loki/SIEM ingestion
# Outputs JSON-structured audit events to Python logging (collected by Promtail)
audit_structured_logger = logging.getLogger("sentinel.audit")


class AuditLogger:
    """Singleton audit logging service."""

    _instance = None
    _lock = threading.Lock()
    _write_lock = threading.Lock()

    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super(AuditLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize audit logger with file storage."""
        if self._initialized:
            return

        self.log_file = Path(__file__).parent.parent / "data" / "audit_log.json"
        self.max_entries = 1000  # Rotate oldest entries out
        self.buffer: List[AuditLogEntry] = []
        self.buffer_size = 10  # Flush after 10 entries
        self._load_existing_logs()

        self._initialized = True
        logger.info(f"Audit logger initialized. Log file: {self.log_file}")

    def _load_existing_logs(self) -> None:
        """Load existing audit logs from file."""
        try:
            if self.log_file.exists():
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    # Load last N entries to respect max_entries
                    entries_data = data.get("entries", [])
                    if len(entries_data) > self.max_entries:
                        entries_data = entries_data[-self.max_entries:]

                    self.buffer = [AuditLogEntry.from_dict(entry) for entry in entries_data]
                logger.info(f"Loaded {len(self.buffer)} existing audit log entries")
            else:
                # Create empty log file
                self._save_logs([])
                logger.info("Created new audit log file")
        except Exception as e:
            logger.error(f"Failed to load audit logs: {e}")
            self.buffer = []

    def _save_logs(self, entries: List[AuditLogEntry]) -> None:
        """Save audit logs to file."""
        try:
            # Ensure data directory exists
            self.log_file.parent.mkdir(exist_ok=True, parents=True)

            with open(self.log_file, 'w') as f:
                data = {
                    "updated_at": datetime.now().isoformat(),
                    "entry_count": len(entries),
                    "entries": [entry.to_dict() for entry in entries]
                }
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save audit logs: {e}")

    def _flush_buffer(self) -> None:
        """Flush buffer to disk."""
        with self._write_lock:
            if not self.buffer:
                return

            # Load existing logs
            existing_entries = []
            if self.log_file.exists():
                try:
                    with open(self.log_file, 'r') as f:
                        data = json.load(f)
                        existing_entries = [AuditLogEntry.from_dict(entry) for entry in data.get("entries", [])]
                except Exception as e:
                    logger.error(f"Failed to read existing logs for flush: {e}")
                    existing_entries = []

            # Combine and limit to max_entries
            all_entries = existing_entries + self.buffer
            if len(all_entries) > self.max_entries:
                all_entries = all_entries[-self.max_entries:]

            # Save combined logs
            self._save_logs(all_entries)
            self.buffer = []  # Clear buffer after successful save
            logger.debug(f"Flushed {len(all_entries) - len(existing_entries)} audit log entries to disk")

    def log_control_action(
        self,
        device_id: str,
        point_name: str,
        user: str,
        old_value: Any,
        new_value: Any,
        result: AuditResultType,
        safety_validation: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a device control action.

        Args:
            device_id: Device identifier
            point_name: Device point name
            user: User ID or "system"
            old_value: Previous value
            new_value: New value being set
            result: Result of the control action
            safety_validation: Safety validation details
            error_message: Error message if failed
            correlation_id: Correlation ID for grouping related actions
            metadata: Additional context

        Returns:
            Audit log entry ID
        """
        entry = AuditLogEntry(
            action=AuditActionType.DEVICE_CONTROL,
            user=user,
            device_id=device_id,
            point_name=point_name,
            old_value=old_value,
            new_value=new_value,
            result=result,
            safety_validation=safety_validation,
            error_message=error_message,
            correlation_id=correlation_id,
            metadata=metadata or {}
        )

        return self._add_entry(entry)

    def log_safety_validation(
        self,
        device_id: str,
        user: str,
        validation_result: Dict[str, Any],
        result: AuditResultType,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a safety validation event.

        Args:
            device_id: Device identifier
            user: User ID or "system"
            validation_result: Safety validation details
            result: Validation result
            correlation_id: Correlation ID
            metadata: Additional context

        Returns:
            Audit log entry ID
        """
        entry = AuditLogEntry(
            action=AuditActionType.SAFETY_VALIDATION,
            user=user,
            device_id=device_id,
            result=result,
            safety_validation=validation_result,
            correlation_id=correlation_id,
            metadata=metadata or {}
        )

        return self._add_entry(entry)

    def log_system_event(
        self,
        event_type: str,
        user: str = "system",
        result: AuditResultType = AuditResultType.SUCCESS,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a system event.

        Args:
            event_type: Type of system event
            user: User ID or "system"
            result: Event result
            error_message: Error message if failed
            metadata: Additional context

        Returns:
            Audit log entry ID
        """
        entry = AuditLogEntry(
            action=AuditActionType.SYSTEM_EVENT,
            user=user,
            result=result,
            error_message=error_message,
            metadata={"event_type": event_type, **(metadata or {})}
        )

        return self._add_entry(entry)

    def log_security_event(
        self,
        event_type: str,
        severity: str = "info",
        user: str = "system",
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        result: AuditResultType = AuditResultType.SUCCESS,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a security-relevant event with structured output.

        BMS-specific security event types:
        - DEVICE_CONTROL: Device setpoint or state change
        - SAFETY_OVERRIDE: Safety rule override attempt
        - BMS_COMMAND: BMS command execution
        - SETPOINT_CHANGE: Critical setpoint modification
        - ACCESS_DENIED: Authorization failure
        - AUTH_FAILURE: Authentication failure
        - SUSPICIOUS_REQUEST: Suspicious request pattern detected
        - CONFIG_CHANGE: System configuration change

        Args:
            event_type: Security event classification
            severity: Event severity (critical, high, medium, low, info)
            user: User ID or "system"
            source_ip: Client IP address
            user_agent: Client user agent string
            result: Event result
            error_message: Error details if applicable
            metadata: Additional event context
        """
        entry = AuditLogEntry(
            action=AuditActionType.SYSTEM_EVENT,
            user=user,
            result=result,
            error_message=error_message,
            metadata={
                "event_type": event_type,
                "severity": severity,
                "source_ip": source_ip,
                "user_agent": user_agent,
                **(metadata or {})
            }
        )

        entry_id = self._add_entry(entry)

        # Also emit to structured logger for Loki/SIEM
        self._emit_structured_log(entry, event_type, severity, source_ip, user_agent)

        return entry_id

    def _emit_structured_log(
        self,
        entry: AuditLogEntry,
        event_type: str,
        severity: str,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """Emit structured JSON log for Promtail/Loki ingestion.

        This produces a JSON log line that Promtail can parse and
        label for efficient querying in Grafana/Loki.
        """
        try:
            structured_event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "audit_id": entry.id,
                "event_type": event_type,
                "severity": severity,
                "action": entry.action.value,
                "user": entry.user,
                "device_id": entry.device_id,
                "point_name": entry.point_name,
                "result": entry.result.value,
                "source_ip": source_ip,
                "user_agent": user_agent[:200] if user_agent else None,
                "correlation_id": entry.correlation_id,
                "component": "sentinel-audit",
                "error_message": entry.error_message,
                "metadata": entry.metadata
            }

            log_message = json.dumps(structured_event, default=str)

            if severity in ("critical", "high"):
                audit_structured_logger.warning(log_message)
            elif severity == "medium":
                audit_structured_logger.info(log_message)
            else:
                audit_structured_logger.debug(log_message)
        except Exception as e:
            logger.error(f"Failed to emit structured audit log: {e}")

    def _add_entry(self, entry: AuditLogEntry) -> str:
        """Add entry to buffer and flush if needed."""
        with self._lock:
            self.buffer.append(entry)

            # Flush if buffer is full
            if len(self.buffer) >= self.buffer_size:
                self._flush_buffer()

            logger.debug(f"Logged audit entry: {entry.action} for {entry.device_id or 'system'} - {entry.result}")
            return entry.id

    def get_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        device_id: Optional[str] = None,
        action: Optional[AuditActionType] = None,
        user: Optional[str] = None,
        result: Optional[AuditResultType] = None,
        limit: int = 100
    ) -> List[AuditLogEntry]:
        """
        Get audit logs with filtering.

        Args:
            start_time: Start time filter
            end_time: End time filter
            device_id: Device ID filter
            action: Action type filter
            user: User filter
            result: Result filter
            limit: Maximum number of entries to return

        Returns:
            List of filtered audit log entries
        """
        # Load all logs (existing + buffer)
        all_entries = []
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    all_entries = [AuditLogEntry.from_dict(entry) for entry in data.get("entries", [])]
            except Exception as e:
                logger.error(f"Failed to read logs for query: {e}")
                all_entries = []

        # Add buffered entries
        all_entries.extend(self.buffer)

        # Apply filters
        filtered = []
        for entry in all_entries:
            if start_time and entry.timestamp < start_time:
                continue
            if end_time and entry.timestamp > end_time:
                continue
            if device_id and entry.device_id != device_id:
                continue
            if action and entry.action != action:
                continue
            if user and entry.user != user:
                continue
            if result and entry.result != result:
                continue
            filtered.append(entry)

        # Sort by timestamp (newest first) and limit
        filtered.sort(key=lambda x: x.timestamp, reverse=True)
        return filtered[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Get audit log statistics."""
        # Load all logs
        all_entries = []
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    all_entries = [AuditLogEntry.from_dict(entry) for entry in data.get("entries", [])]
            except Exception as e:
                logger.error(f"Failed to read logs for stats: {e}")
                all_entries = []

        # Add buffered entries
        all_entries.extend(self.buffer)

        if not all_entries:
            return {
                "total_entries": 0,
                "by_action": {},
                "by_result": {},
                "by_user": {},
                "recent_activity": []
            }

        # Calculate statistics
        by_action = {}
        by_result = {}
        by_user = {}

        for entry in all_entries:
            by_action[entry.action.value] = by_action.get(entry.action.value, 0) + 1
            by_result[entry.result.value] = by_result.get(entry.result.value, 0) + 1
            by_user[entry.user] = by_user.get(entry.user, 0) + 1

        # Get recent activity (last 24 hours)
        one_day_ago = datetime.now().timestamp() - 24 * 3600
        recent = [entry for entry in all_entries if entry.timestamp.timestamp() > one_day_ago]

        return {
            "total_entries": len(all_entries),
            "by_action": by_action,
            "by_result": by_result,
            "by_user": by_user,
            "recent_activity_count": len(recent),
            "last_updated": datetime.now().isoformat()
        }

    def flush(self) -> None:
        """Force flush buffer to disk."""
        self._flush_buffer()

    def clear(self) -> None:
        """Clear all audit logs (for testing/demo reset)."""
        with self._lock:
            self.buffer = []
            self._save_logs([])
            logger.info("Cleared all audit logs")