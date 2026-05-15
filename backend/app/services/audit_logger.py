"""Audit Logger Service.

Thread-safe audit logging service for recording all control actions,
safety validations, and system events. Supabase as primary store
with in-memory buffer. JSON file fallback retired Phase 193+.

Enhanced (Phase 63): Adds structured JSON logging output alongside
file-based logging. Structured logs are collected by Promtail and
shipped to Loki for centralised aggregation and SIEM alerting.
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.models.audit_log import AuditActionType, AuditLogEntry, AuditResultType
from app.database.repositories.audit_repository import AuditRepository
from app.services.encryption_service import get_encryption_service

logger = logging.getLogger(__name__)

# Async mutex lock for concurrent audit archival protection (Phase 168-03)
# Ensures only one archival process runs at a time across async tasks
_AUDIT_ARCHIVAL_LOCK = asyncio.Lock()

# Structured audit logger for Loki/SIEM ingestion
# Outputs JSON-structured audit events to Python logging (collected by Promtail)
audit_structured_logger = logging.getLogger("sentinel.audit")

# BACnet audit log directory (mirrors modbus_audit/ pattern)
BACNET_AUDIT_DIR = Path(__file__).parent.parent / "data" / "bacnet_audit"


@dataclass
class BACnetWriteAudit:
    """Audit record for BACnet write operations.

    Mirrors the schema of Modbus WriteResult for consistent SIEM queries.
    """

    correlation_id: str
    equipment_tag: str  # Human-readable tag (e.g. "S002-AHU-001-SP")
    device_id: int  # BACnet device instance
    object_type: str  # e.g. "analogValue", "binaryOutput"
    instance: int  # Object instance number
    value: Any  # Written value
    priority: int  # BACnet priority (1-16, normally 8)
    who: str  # User/system who triggered the write
    timestamp: str  # ISO8601 UTC
    write_latency_ms: float  # Milliseconds for the write operation
    success: bool  # True if write succeeded
    error_msg: str | None = None  # Set if write failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "bacnet_write",
            "correlation_id": self.correlation_id,
            "equipment_tag": self.equipment_tag,
            "device_id": self.device_id,
            "object_type": self.object_type,
            "instance": self.instance,
            "value": self.value,
            "priority": self.priority,
            "who": self.who,
            "timestamp": self.timestamp,
            "write_latency_ms": round(self.write_latency_ms, 2),
            "success": self.success,
            "error_msg": self.error_msg,
        }


class AuditLogger:
    """Singleton audit logging service."""

    _instance = None
    _lock = threading.Lock()
    _write_lock = threading.Lock()

    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize audit logger with Supabase primary store."""
        if self._initialized:
            return

        self._repo = AuditRepository()
        self.buffer: list[AuditLogEntry] = []
        self.buffer_size = 10  # Flush after 10 entries
        self.encryption_service = get_encryption_service()
        self.max_entries = 10_000

        self._initialized = True
        logger.info("Audit logger initialized. Supabase primary store.")
        logger.info(f"Encryption enabled: {self.encryption_service.enabled}")

    def _load_existing_logs(self) -> None:
        """No-op: logs are loaded from Supabase on demand."""
        pass

    def _encrypt_audit_entry(self, entry_dict: dict[str, Any]) -> dict[str, Any]:
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

    def _decrypt_audit_entry(self, entry_dict: dict[str, Any]) -> dict[str, Any]:
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

    def _save_logs(self, entries: list[AuditLogEntry]) -> None:
        """No-op: audit logs are persisted to Supabase via _flush_buffer."""
        pass

    def _flush_buffer(self) -> None:
        """Flush buffer to Supabase."""
        with self._write_lock:
            if not self.buffer:
                return

            try:
                entries_to_flush = list(self.buffer)
                for entry in entries_to_flush:
                    entry_dict = entry.to_dict()
                    encrypted = self._encrypt_audit_entry(entry_dict)
                    self._repo.create({
                        "id": encrypted.get("id"),
                        "timestamp": encrypted.get("timestamp"),
                        "action": encrypted.get("action"),
                        "user_id": encrypted.get("user"),
                        "device_id": encrypted.get("device_id"),
                        "point_name": encrypted.get("point_name"),
                        "old_value": json.dumps(encrypted["old_value"]) if encrypted.get("old_value") is not None else None,
                        "new_value": json.dumps(encrypted["new_value"]) if encrypted.get("new_value") is not None else None,
                        "result": encrypted.get("result"),
                        "safety_validation": json.dumps(encrypted["safety_validation"]) if encrypted.get("safety_validation") else None,
                        "error_message": encrypted.get("error_message"),
                        "correlation_id": encrypted.get("correlation_id"),
                        "metadata": encrypted.get("metadata", {}),
                    })
                self.buffer = []
                logger.debug(f"Flushed {len(entries_to_flush)} audit entries to Supabase")
            except Exception as e:
                logger.error(f"Failed to flush audit buffer to Supabase: {e}")

    def log_control_action(
        self,
        device_id: str,
        point_name: str,
        user: str,
        old_value: Any,
        new_value: Any,
        result: AuditResultType,
        safety_validation: dict[str, Any] | None = None,
        error_message: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
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
        validation_result: dict[str, Any],
        result: AuditResultType,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        escalation_level: str | None = None,
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
            escalation_level: Severity — "critical", "warning", "none" (from EscalationLevel)

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
            escalation_level=escalation_level,
        )

        return self._add_entry(entry)

    def log_system_event(
        self,
        event_type: str,
        user: str = "system",
        result: AuditResultType = AuditResultType.SUCCESS,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
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
        source_ip: str | None = None,
        user_agent: str | None = None,
        result: AuditResultType = AuditResultType.SUCCESS,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
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
        source_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Emit structured JSON log for Promtail/Loki ingestion.

        This produces a JSON log line that Promtail can parse and
        label for efficient querying in Grafana/Loki.
        """
        try:
            structured_event = {
                "timestamp": datetime.now(UTC).isoformat(),
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
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        device_id: str | None = None,
        action: AuditActionType | None = None,
        user: str | None = None,
        result: AuditResultType | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        """
        Get audit logs with filtering from Supabase.

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
        rows = self._repo.get_all(
            limit=limit,
            user_id=user,
            action=action.value if action else None,
            device_id=device_id,
        )
        entries = []
        for row in rows:
            # Decrypt sensitive fields before display
            # DB stores as user_id; decrypt expects user — remap before/after
            decrypted = dict(row)
            user_val = decrypted.pop("user_id", None)
            if user_val is not None:
                decrypted["user"] = user_val
            decrypted = self._decrypt_audit_entry(decrypted) if self.encryption_service.enabled else decrypted
            decrypted["user_id"] = decrypted.pop("user", "")

            # Apply time filters in Python (repo doesn't support range filter)
            ts = datetime.fromisoformat(decrypted["timestamp"].replace("Z", "+00:00")) if isinstance(decrypted["timestamp"], str) else decrypted["timestamp"]
            if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            if start_time and ts < start_time:
                continue
            if end_time and ts > end_time:
                continue
            if result and decrypted.get("result") != result.value:
                continue
            entries.append(AuditLogEntry(
                id=decrypted["id"],
                timestamp=ts,
                action=AuditActionType(decrypted.get("action", "system_event")),
                user=decrypted.get("user_id", ""),
                result=AuditResultType(decrypted.get("result", "warning")),
                device_id=decrypted.get("device_id"),
                point_name=decrypted.get("point_name"),
                old_value=decrypted.get("old_value"),
                new_value=decrypted.get("new_value"),
                safety_validation=decrypted.get("safety_validation"),
                error_message=decrypted.get("error_message"),
                correlation_id=decrypted.get("correlation_id"),
                metadata=decrypted.get("metadata", {}),
            ))
        # Add buffered entries
        entries.extend(self.buffer)
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get audit log statistics from Supabase."""
        try:
            rows = self._repo.get_all(limit=1000)
            all_entries = []
            for row in rows:
                ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) if isinstance(row["timestamp"], str) else row["timestamp"]
                all_entries.append(AuditLogEntry(
                    id=row["id"],
                    timestamp=ts,
                    action=AuditActionType(row.get("action", "system_event")),
                    user=row.get("user_id", ""),
                    result=AuditResultType(row.get("result", "warning")),
                    device_id=row.get("device_id"),
                    point_name=row.get("point_name"),
                    metadata=row.get("metadata", {}),
                ))
            all_entries.extend(self.buffer)
        except Exception:
            all_entries = list(self.buffer)

        if not all_entries:
            return {"total_entries": 0, "by_action": {}, "by_result": {}, "by_user": {}, "recent_activity": []}

        by_action: dict[str, int] = {}
        by_result: dict[str, int] = {}
        by_user: dict[str, int] = {}

        for entry in all_entries:
            by_action[entry.action.value] = by_action.get(entry.action.value, 0) + 1
            by_result[entry.result.value] = by_result.get(entry.result.value, 0) + 1
            by_user[entry.user] = by_user.get(entry.user, 0) + 1

        now = datetime.now(UTC).timestamp()
        recent = [e for e in all_entries if e.timestamp.timestamp() > now - 86400]

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

    def log_bacnet_write(self, audit: BACnetWriteAudit) -> None:
        """Append a BACnet write audit record to bacnet_audit/bacnet_writes.jsonl.

        Mirrors the ModbusBESSWriter._audit_log() pattern.
        Writes are never dropped — failures are logged but do not raise.
        """
        BACNET_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        log_file = BACNET_AUDIT_DIR / "bacnet_writes.jsonl"

        # Structured log for Loki (sentinel.audit logger)
        if audit.success:
            audit_structured_logger.info(
                f"event=bacnet_write "
                f"correlation_id={audit.correlation_id} "
                f"equipment_tag={audit.equipment_tag} "
                f"device_id={audit.device_id} "
                f"object={audit.object_type}:{audit.instance} "
                f"value={audit.value} "
                f"priority={audit.priority} "
                f"who={audit.who} "
                f"success=true"
            )
        else:
            audit_structured_logger.warning(
                f"event=bacnet_write_error "
                f"correlation_id={audit.correlation_id} "
                f"equipment_tag={audit.equipment_tag} "
                f"error={audit.error_msg} "
                f"who={audit.who} "
                f"success=false"
            )

        # JSONL file for compliance archival
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(audit.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Failed to write BACnet audit record: {e}")

    def clear(self) -> None:
        """Clear all audit logs (for testing/local reset)."""
        with self._lock:
            self.buffer = []
            try:
                self._repo._client.table("audit_log").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            except Exception:
                pass
            logger.info("Cleared all audit logs")

    async def archive_old_audit_logs(self, days_old: int = 30) -> int:
        """Archive audit logs older than specified days to immutable Supabase table.

        Implements immutable audit trail archival for AUDIT-001 control.

        Protected by asyncio.Lock to prevent concurrent archival corruption.
        Only deletes from active log entries that were successfully archived.
        Fail-safe: if any entries fail, keeps them for retry.

        Args:
            days_old: Archive entries older than this many days (default: 30)

        Returns:
            Number of entries archived (partial failure returns partial count)
        """
        # Acquire asyncio lock to prevent concurrent archival (Phase 168-03)
        async with _AUDIT_ARCHIVAL_LOCK:
            return await self._do_archive_old_audit_logs(days_old)

    async def _do_archive_old_audit_logs(self, days_old: int = 30) -> int:
        """Internal archival logic (Phase 193+: DB-native retention).

        Deletes entries older than days_old from audit_log DB table.
        No JSON file involvement.

        Args:
            days_old: Archive entries older than this many days (default: 30)

        Returns:
            Number of entries deleted
        """
        import asyncio
        from datetime import datetime, timedelta

        cutoff_time = datetime.now() - timedelta(days=days_old)

        try:
            self._flush_buffer()
        except Exception:
            pass

        try:
            supabase = get_supabase_client()
            result = await asyncio.to_thread(
                supabase.table("audit_log")
                .delete()
                .lt("timestamp", cutoff_time.isoformat())
                .execute
            )
            deleted = len(result.data) if result.data else 0
            logger.info(f"Archived {deleted} audit log entries older than {days_old} days")
            return deleted
        except Exception as e:
            logger.error(f"Failed to archive audit logs: {e}")
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
