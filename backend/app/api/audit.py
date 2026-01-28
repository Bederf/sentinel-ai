"""Audit API Endpoints.

API endpoints for querying audit logs and statistics.
Provides filtering by time, device, action, user, and result.
"""

import logging
from datetime import datetime
from typing import Optional, List, Any

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from app.services.audit_logger import AuditLogger
from app.models.audit_log import AuditActionType, AuditResultType, AuditLogEntry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/audit", tags=["audit"])

# Initialize audit logger
audit_logger = AuditLogger()


# Response models
class AuditLogEntryResponse(BaseModel):
    """Audit log entry response model."""
    id: str
    timestamp: datetime
    action: str
    user: str
    device_id: Optional[str] = None
    point_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    result: str
    safety_validation: Optional[dict] = None
    error_message: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    @classmethod
    def from_entry(cls, entry: AuditLogEntry) -> "AuditLogEntryResponse":
        """Create response from audit log entry."""
        return cls(
            id=entry.id,
            timestamp=entry.timestamp,
            action=entry.action.value,
            user=entry.user,
            device_id=entry.device_id,
            point_name=entry.point_name,
            old_value=entry.old_value,
            new_value=entry.new_value,
            result=entry.result.value,
            safety_validation=entry.safety_validation,
            error_message=entry.error_message,
            correlation_id=entry.correlation_id,
            metadata=entry.metadata
        )


class AuditLogsResponse(BaseModel):
    """Audit logs response with pagination."""
    entries: List[AuditLogEntryResponse]
    total_count: int
    page: int
    page_size: int
    has_more: bool


class AuditStatsResponse(BaseModel):
    """Audit statistics response."""
    total_entries: int
    by_action: dict
    by_result: dict
    by_user: dict
    recent_activity_count: int
    last_updated: datetime


# API endpoints
@router.get("/logs", response_model=AuditLogsResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    start_time: Optional[datetime] = Query(None, description="Start time filter"),
    end_time: Optional[datetime] = Query(None, description="End time filter"),
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    action: Optional[AuditActionType] = Query(None, description="Filter by action type"),
    user: Optional[str] = Query(None, description="Filter by user"),
    result: Optional[AuditResultType] = Query(None, description="Filter by result"),
) -> AuditLogsResponse:
    """
    Get audit logs with filtering and pagination.

    Returns audit log entries sorted by timestamp (newest first).
    """
    try:
        # Calculate offset for pagination
        offset = (page - 1) * page_size
        limit = page_size + 1  # Get one extra to check if there are more

        # Get filtered logs
        logs = audit_logger.get_logs(
            start_time=start_time,
            end_time=end_time,
            device_id=device_id,
            action=action,
            user=user,
            result=result,
            limit=limit
        )

        # Check if there are more results
        has_more = len(logs) > page_size
        if has_more:
            logs = logs[:page_size]  # Remove the extra item

        # Convert to response models
        entries = [AuditLogEntryResponse.from_entry(log) for log in logs]

        # For demo, estimate total count (in production would use database count)
        total_count = len(logs) + (page_size if has_more else 0)

        return AuditLogsResponse(
            entries=entries,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_more=has_more
        )

    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get audit logs: {str(e)}")


@router.get("/logs/{entry_id}", response_model=AuditLogEntryResponse)
async def get_audit_log_entry(entry_id: str) -> AuditLogEntryResponse:
    """
    Get a specific audit log entry by ID.

    Returns the full audit log entry details.
    """
    try:
        # Get all logs and find the specific entry
        logs = audit_logger.get_logs(limit=1000)  # Get enough to find the entry
        entry = next((log for log in logs if log.id == entry_id), None)

        if not entry:
            raise HTTPException(status_code=404, detail=f"Audit log entry {entry_id} not found")

        return AuditLogEntryResponse.from_entry(entry)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit log entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get audit log entry: {str(e)}")


@router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats() -> AuditStatsResponse:
    """
    Get audit log statistics.

    Returns counts by action type, result, user, and recent activity.
    """
    try:
        stats = audit_logger.get_stats()

        # Parse last_updated from stats
        last_updated = datetime.fromisoformat(stats["last_updated"]) if isinstance(stats["last_updated"], str) else stats["last_updated"]

        return AuditStatsResponse(
            total_entries=stats["total_entries"],
            by_action=stats["by_action"],
            by_result=stats["by_result"],
            by_user=stats["by_user"],
            recent_activity_count=stats["recent_activity_count"],
            last_updated=last_updated
        )

    except Exception as e:
        logger.error(f"Failed to get audit stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get audit stats: {str(e)}")


@router.get("/demo-data")
async def generate_demo_audit_data() -> dict:
    """
    Generate demo audit data for testing and demonstration.

    Creates 50-100 historical audit log entries with variety:
    - Successful device controls
    - Safety-blocked actions
    - Warnings
    - System events
    - Different users and devices
    """
    try:
        from datetime import timedelta
        import random

        logger.info("Generating demo audit data...")

        # Demo devices
        demo_devices = [
            "chiller-gateway-001",
            "ahu-level3-002",
            "lighting-lobby-003",
            "access-main-004",
            "fire-pump-005",
            "vav-office-006"
        ]

        # Demo users
        demo_users = ["operator-1", "operator-2", "system", "scheduler", "admin"]

        # Demo points
        demo_points = ["setpoint", "fan_speed", "brightness", "status", "mode"]

        # Generate entries for last 7 days
        entries_created = 0
        now = datetime.now()

        for days_ago in range(7):
            for _ in range(random.randint(5, 15)):  # 5-15 entries per day
                # Random timestamp within the day
                hours_ago = random.randint(0, 23)
                minutes_ago = random.randint(0, 59)
                timestamp = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)

                # Random device and user
                device_id = random.choice(demo_devices)
                user = random.choice(demo_users)
                point_name = random.choice(demo_points)

                # Random old and new values
                old_value = random.randint(20, 25) if "setpoint" in point_name else random.randint(50, 100)
                new_value = old_value + random.randint(-5, 5)

                # Random result (weighted toward success)
                result_weights = {
                    AuditResultType.SUCCESS: 70,
                    AuditResultType.WARNING: 15,
                    AuditResultType.BLOCKED: 10,
                    AuditResultType.FAILED: 5
                }
                result = random.choices(
                    list(result_weights.keys()),
                    weights=list(result_weights.values())
                )[0]

                # Create safety validation based on result
                safety_validation = None
                error_message = None

                if result == AuditResultType.BLOCKED:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "pressure_limits"],
                        "passed_rules": ["temperature_range"],
                        "failed_rules": ["pressure_limits"],
                        "details": "Pressure exceeds safe operating limits"
                    }
                    error_message = "Safety validation failed: Pressure limit exceeded"
                elif result == AuditResultType.WARNING:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "minimum_runtime"],
                        "passed_rules": ["temperature_range"],
                        "warnings": ["minimum_runtime"],
                        "details": "Minimum runtime requirement not met (warning only)"
                    }
                elif result == AuditResultType.SUCCESS:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "pressure_limits"],
                        "passed_rules": ["temperature_range", "pressure_limits"],
                        "details": "All safety checks passed"
                    }

                # Log the demo entry
                audit_logger.log_control_action(
                    device_id=device_id,
                    point_name=point_name,
                    user=user,
                    old_value=old_value,
                    new_value=new_value,
                    result=result,
                    safety_validation=safety_validation,
                    error_message=error_message,
                    metadata={
                        "demo_data": True,
                        "generated_at": timestamp.isoformat(),
                        "priority": random.randint(8, 16)
                    }
                )
                entries_created += 1

        # Force flush to disk
        audit_logger.flush()

        logger.info(f"Generated {entries_created} demo audit entries")

        return {
            "status": "success",
            "entries_created": entries_created,
            "message": f"Generated {entries_created} demo audit log entries spanning last 7 days"
        }

    except Exception as e:
        logger.error(f"Failed to generate demo audit data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate demo audit data: {str(e)}")