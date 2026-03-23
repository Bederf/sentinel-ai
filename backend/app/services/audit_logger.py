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
from filelock import FileLock

from app.models.audit_log import AuditLogEntry, AuditActionType, AuditResultType
from app.services.encryption_service import get_encryption_service

logger = logging.getLogger(__name__)

# File lock for concurrent archival safety (Phase 168-03)
ARCHIVAL_LOCK_PATH = "/tmp/sentinel_audit_archival.lock"
_archival_lock = FileLock(ARCHIVAL_LOCK_PATH, timeout=60)

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
        # Import from security constants — increased from 1000 to 10_000 (Phase 137-09)
        try:
            from app.security.constants import LOG_MAX_ENTRIES

            self.max_entries = LOG_MAX_ENTRIES
        except ImportError:
            self.max_entries = 10_000
        self.buffer: List[AuditLogEntry] = []
        self.buffer_size = 10  # Flush after 10 entries
        self.encryption_service = get_encryption_service()
        self._load_existing_logs()

        self._initialized = True
        logger.info(f"Audit logger initialized. Log file: {self.log_file}")
        logger.info(f"Encryption enabled: {self.encryption_service.enabled}")

    def _load_existing_logs(self) -> None:
        """Load existing audit logs from file."""
        try:
            if self.log_file.exists():
                with open(self.log_file, "r") as f:
                    data = json.load(f)
                    # Load last N entries to respect max_entries
                    entries_data = data.get("entries", [])
                    if len(entries_data) > self.max_entries:
                        entries_data = entries_data[-self.max_entries :]

                    # Decrypt sensitive fields if encryption is enabled
                    decrypted_entries = []
                    for entry in entries_data:
                        decrypted_entry = self._decrypt_audit_entry(entry)
                        decrypted_entries.append(AuditLogEntry.from_dict(decrypted_entry))
                    self.buffer = decrypted_entries
                logger.info(f"Loaded {len(self.buffer)} existing audit log entries")
            else:
                # Create empty log file
                self._save_logs([])
                logger.info("Created new audit log file")
        except Exception as e:
            logger.error(f"Failed to load audit logs: {e}")
            self.buffer = []

    def _encrypt_audit_entry(self, entry_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive fields in audit log entry.

        Encrypts: user, device_id, point_name, old_value, new_value, error_message
        """
        if not self.encryption_service.enabled:
            return entry_dict

        encrypted = entry_dict.copy()

        # List of sensitive fields to encrypt
        sensitive_fields = ["user", "device_id", "point_name", "error_message"]

        for field in sensitive_fields:
            if field in encrypted and encrypted[field] and isinstance(encrypted[field], str):
                encrypted[field] = self.encryption_service.encrypt(encrypted[field])

        # Encrypt value fields (might contain sensitive data)
        if encrypted.get("old_value") is not None:
            encrypted["old_value"] = self._encrypt_value(encrypted["old_value"])
        if encrypted.get("new_value") is not None:
            encrypted["new_value"] = self._encrypt_value(encrypted["new_value"])

        return encrypted

    def _decrypt_audit_entry(self, entry_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive fields in audit log entry."""
        if not self.encryption_service.enabled:
            return entry_dict

        decrypted = entry_dict.copy()

        # List of sensitive fields to decrypt
        sensitive_fields = ["user", "device_id", "point_name", "error_message"]

        for field in sensitive_fields:
            if field in decrypted and decrypted[field] and isinstance(decrypted[field], str):
                decrypted[field] = self.encryption_service.decrypt(decrypted[field])

        # Decrypt value fields
        if decrypted.get("old_value") is not None:
            decrypted["old_value"] = self._decrypt_value(decrypted["old_value"])
        if decrypted.get("new_value") is not None:
            decrypted["new_value"] = self._decrypt_value(decrypted["new_value"])

        return decrypted

    def _encrypt_value(self, value: Any) -> Any:
        """Encrypt a value (handles strings and other types)."""
        if isinstance(value, str):
            return self.encryption_service.encrypt(value)
        elif isinstance(value, (int, float, bool, type(None))):
            return value  # Don't encrypt primitive types
        else:
            # Serialize complex types as JSON, then encrypt
            try:
                serialized = json.dumps(value, default=str)
                return {"_encrypted_json": self.encryption_service.encrypt(serialized)}
            except Exception as e:
                logger.warning(f"Failed to encrypt complex value: {e}")
                return value

    def _decrypt_value(self, value: Any) -> Any:
        """Decrypt a value (handles strings and other types)."""
        if isinstance(value, str):
            return self.encryption_service.decrypt(value)
        elif isinstance(value, dict) and "_encrypted_json" in value:
            # Decrypt and deserialize JSON
            try:
                decrypted_json = self.encryption_service.decrypt(value["_encrypted_json"])
                return json.loads(decrypted_json)
            except Exception as e:
                logger.warning(f"Failed to decrypt complex value: {e}")
                return value
        else:
            return value  # Return as-is for primitive types

    def _save_logs(self, entries: List[AuditLogEntry]) -> None:
        """Save audit logs to file with encryption."""
        try:
            # Ensure data directory exists
            self.log_file.parent.mkdir(exist_ok=True, parents=True)

            # Encrypt entries before saving
            encrypted_entries = []
            for entry in entries:
                entry_dict = entry.to_dict()
                encrypted_entry = self._encrypt_audit_entry(entry_dict)
                encrypted_entries.append(encrypted_entry)

            with open(self.log_file, "w") as f:
                data = {
                    "updated_at": datetime.now().isoformat(),
                    "entry_count": len(encrypted_entries),
                    "encryption_enabled": self.encryption_service.enabled,
                    "entries": encrypted_entries,
                }
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save audit logs: {e}")

    def _flush_buffer(self) -> None:
        """Flush buffer to disk."""
        with self._write_lock:
            if not self.buffer:
                return

            # Load existing logs (decrypted)
            existing_entries = []
            if self.log_file.exists():
                try:
                    with open(self.log_file, "r") as f:
                        data = json.load(f)
                        # Decrypt entries when loading for merge
                        for entry in data.get("entries", []):
                            decrypted_entry = self._decrypt_audit_entry(entry)
                            existing_entries.append(AuditLogEntry.from_dict(decrypted_entry))
                except Exception as e:
                    logger.error(f"Failed to read existing logs for flush: {e}")
                    existing_entries = []

            # Combine and limit to max_entries
            all_entries = existing_entries + self.buffer
            if len(all_entries) > self.max_entries:
                all_entries = all_entries[-self.max_entries :]

            # Save combined logs (encryption happens in _save_logs)
            self._save_logs(all_entries)
            self.buffer = []  # Clear buffer after successful save
            logger.debug(f"Flushed {len(self.buffer)} audit log entries to disk")

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
        metadata: Optional[Dict[str, Any]] = None,
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
            metadata=metadata or {},
        )

        return self._add_entry(entry)

    def log_safety_validation(
        self,
        device_id: str,
        user: str,
        validation_result: Dict[str, Any],
        result: AuditResultType,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
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
            metadata=metadata or {},
        )

        return self._add_entry(entry)

    def log_system_event(
        self,
        event_type: str,
        user: str = "system",
        result: AuditResultType = AuditResultType.SUCCESS,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
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
            metadata={"event_type": event_type, **(metadata or {})},
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
        metadata: Optional[Dict[str, Any]] = None,
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
                **(metadata or {}),
            },
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
        user_agent: Optional[str] = None,
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
                "metadata": entry.metadata,
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
        limit: int = 100,
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
                with open(self.log_file, "r") as f:
                    data = json.load(f)
                    # Decrypt entries when loading
                    for entry in data.get("entries", []):
                        decrypted_entry = self._decrypt_audit_entry(entry)
                        all_entries.append(AuditLogEntry.from_dict(decrypted_entry))
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
                with open(self.log_file, "r") as f:
                    data = json.load(f)
                    # Decrypt entries when loading
                    for entry in data.get("entries", []):
                        decrypted_entry = self._decrypt_audit_entry(entry)
                        all_entries.append(AuditLogEntry.from_dict(decrypted_entry))
            except Exception as e:
                logger.error(f"Failed to read logs for stats: {e}")
                all_entries = []

        # Add buffered entries
        all_entries.extend(self.buffer)

        if not all_entries:
            return {"total_entries": 0, "by_action": {}, "by_result": {}, "by_user": {}, "recent_activity": []}

        # Calculate statistics
        by_action: Dict[str, int] = {}
        by_result: Dict[str, int] = {}
        by_user: Dict[str, int] = {}

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
            "last_updated": datetime.now().isoformat(),
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

    async def archive_old_audit_logs(self, days_old: int = 30) -> int:
        """Archive audit logs older than specified days to immutable Supabase table.

        Implements immutable audit trail archival for AUDIT-001 control.

        Uses file lock to prevent concurrent archival calls from race conditions.
        Only deletes active log entries if ALL archival succeeded (fail-safe).

        Args:
            days_old: Archive entries older than this many days (default: 30)

        Returns:
            Number of entries archived (partial failure returns partial count)
        """
        import asyncio
        from datetime import datetime, timedelta
        from app.database.supabase_client import get_supabase_client

        # Acquire lock to prevent concurrent archival (Phase 168-03)
        with _archival_lock:
            return await self._do_archive_old_audit_logs(days_old)

    async def _do_archive_old_audit_logs(self, days_old: int = 30) -> int:
        """Internal archival logic (called under lock).

        Args:
            days_old: Archive entries older than this many days

        Returns:
            Number of entries successfully archived
        """
        import asyncio
        from datetime import datetime, timedelta
        from app.database.supabase_client import get_supabase_client

        try:
            self._flush_buffer()  # Ensure all entries are saved first

            # Load all entries from audit log file
            all_entries = []
            if self.log_file.exists():
                try:
                    with open(self.log_file, "r") as f:
                        data = json.load(f)
                        for entry in data.get("entries", []):
                            decrypted_entry = self._decrypt_audit_entry(entry)
                            all_entries.append(AuditLogEntry.from_dict(decrypted_entry))
                except Exception as e:
                    logger.error(f"Failed to read logs for archival: {e}")
                    return 0

            # Identify old entries (older than days_old)
            cutoff_time = datetime.now() - timedelta(days=days_old)
            old_entries = [entry for entry in all_entries if entry.timestamp < cutoff_time]
            new_entries = [entry for entry in all_entries if entry.timestamp >= cutoff_time]

            if not old_entries:
                logger.info(f"No audit entries older than {days_old} days to archive")
                return 0

            # Archive old entries to Supabase (immutable table)
            archived_count = 0
            failed_entries = []

            try:
                supabase = get_supabase_client()
                for entry in old_entries:
                    entry_dict = entry.to_dict()
                    archive_record = {
                        "archived_from": "audit_log.json",
                        "event_data": entry_dict,
                        "created_at": entry.timestamp.isoformat(),
                    }

                    # Insert with upsert to handle duplicates idempotently
                    try:
                        await asyncio.to_thread(supabase.table("audit_archive").upsert(archive_record).execute)
                        archived_count += 1
                    except Exception as e:
                        # Log and track failed entry
                        logger.warning(f"Failed to archive entry {entry.id}: {e}")
                        failed_entries.append(entry)

                logger.info(f"Archived {archived_count}/{len(old_entries)} entries to audit_archive table")
            except Exception as e:
                logger.error(f"Failed to archive to Supabase: {e}")
                # Fallback: don't delete from local file if Supabase fails
                return 0

            # CRITICAL (Phase 168-03): Only delete if ALL succeeded
            if len(failed_entries) == 0:
                # All entries archived successfully; delete from active log
                self._save_logs(new_entries)
                logger.info(
                    f"Removed {archived_count} archived entries from active audit log "
                    f"({len(new_entries)} entries remain)"
                )
            else:
                # Some failed; keep ALL old entries in active log for retry
                logger.warning(
                    f"Archival incomplete: {archived_count}/{len(old_entries)} succeeded. "
                    f"Keeping {len(failed_entries)} failed entries in active log for retry."
                )

            return archived_count

        except Exception as e:
            logger.error(f"Audit log archival failed: {e}")
            return 0

    async def audit_archival_job(self, interval_days: int = 30) -> None:
        """Background job for periodic audit log archival.

        Runs indefinitely, archiving logs monthly (or at specified interval).

        Args:
            interval_days: Interval between archival runs (default: 30 days)
        """
        import asyncio

        logger.info(f"Starting audit archival background job (interval: {interval_days} days)")

        try:
            while True:
                try:
                    # Run archival
                    archived_count = await self.archive_old_audit_logs(days_old=interval_days)
                    logger.info(f"Audit archival job completed: {archived_count} entries archived")

                    # Sleep until next run (interval_days * 86400 seconds)
                    await asyncio.sleep(interval_days * 86400)

                except Exception as e:
                    logger.error(f"Error in audit archival job: {e}")
                    # Sleep briefly and retry to avoid tight loop on errors
                    await asyncio.sleep(300)  # 5 minutes before retry

        except asyncio.CancelledError:
            logger.info("Audit archival job cancelled")
            raise
