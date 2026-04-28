"""
Telemetry verification service for decision execution.

Phase 170-03: Control Actuation Loop — Verification
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.middleware.event_stream import event_stream
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


async def verify_telemetry_change_async(
    decision_id: str,
    site_id: str,
    correlation_id: str,
    expected_change: dict,
) -> bool:
    """
    Poll telemetry for up to 30 seconds to confirm BMS command took effect.

    Runs in background (spawned via asyncio.create_task).
    Emits DECISION_VERIFIED or DECISION_TIMEOUT to SSE stream.

    Args:
        decision_id: Decision ID being executed
        site_id: Site ID
        correlation_id: Correlation ID for audit trail threading
        expected_change: Dict with device_id, point, expected_value

    Returns:
        True if verification succeeded, False if timeout

    Raises:
        None (all errors logged, not propagated)
    """
    audit_logger = AuditLogger()

    try:
        for attempt in range(30):
            try:
                await asyncio.sleep(1)

                # Query telemetry service for current point value
                # TODO: Wire actual telemetry_service.get_point_value() call
                # For now, stub implementation
                actual_value = await get_point_value(
                    device_id=expected_change["device_id"],
                    point=expected_change["point"],
                    site_id=site_id,
                )

                if actual_value == expected_change["expected_value"]:
                    # Success
                    verification_time = attempt + 1
                    await audit_logger.record_event(
                        {
                            "event_type": "DECISION_VERIFIED",
                            "correlation_id": correlation_id,
                            "decision_id": decision_id,
                            "verification_time_seconds": verification_time,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

                    # Push to SSE stream
                    try:
                        await event_stream.emit(
                            event_type="COMMAND_VERIFIED",
                            correlation_id=correlation_id,
                            payload={
                                "decision_id": decision_id,
                                "verification_time": verification_time,
                            },
                        )
                    except Exception as e:
                        logger.warning(f"Failed to emit SSE event for {decision_id}: {e!s}")

                    return True

            except Exception as e:
                # Log error, continue polling
                await audit_logger.record_event(
                    {
                        "event_type": "TELEMETRY_POLL_ERROR",
                        "correlation_id": correlation_id,
                        "decision_id": decision_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                logger.warning(f"Error during telemetry polling (attempt {attempt + 1}): {e!s}")
                # Continue to next attempt

        # Timeout after 30s
        await audit_logger.record_event(
            {
                "event_type": "DECISION_TIMEOUT",
                "correlation_id": correlation_id,
                "decision_id": decision_id,
                "message": "Telemetry did not confirm change within 30s",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # Push timeout to SSE stream
        try:
            await event_stream.emit(
                event_type="COMMAND_TIMEOUT",
                correlation_id=correlation_id,
                payload={"decision_id": decision_id},
            )
        except Exception as e:
            logger.warning(f"Failed to emit timeout SSE event for {decision_id}: {e!s}")

        return False

    except Exception as e:
        logger.error(f"Critical error in verify_telemetry_change_async: {e!s}")
        # Log critical error but don't raise
        await audit_logger.record_event(
            {
                "event_type": "VERIFICATION_CRITICAL_ERROR",
                "correlation_id": correlation_id,
                "decision_id": decision_id,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        return False


async def get_point_value(
    device_id: str,
    point: str,
    site_id: str,
) -> float | None:
    """
    Get current point value from telemetry.

    Queries device manager or telemetry cache for latest point value.

    Args:
        device_id: Device ID (e.g., S002-FCU-L1-A)
        point: Point name (e.g., setpoint, temperature)
        site_id: Site ID

    Returns:
        Current point value or None if not found

    Raises:
        Exception on service errors (caller catches and logs)
    """
    from app.database.client import get_supabase_client
    from app.services.device_manager import DeviceManager

    try:
        # Try device manager first (in-memory, cached)
        device_manager = DeviceManager()
        device = device_manager.get_device(device_id)

        if device:
            # Check if point exists in device's current state
            points = device.get("points", {})
            if isinstance(points, dict) and point in points:
                value = points[point].get("value")
                if value is not None:
                    return float(value)

        # Fallback: query Supabase for latest point value
        supabase = get_supabase_client()
        result = (
            supabase.table("device_telemetry")
            .select("value")
            .eq("device_id", device_id)
            .eq("point_name", point)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )

        if result.data and len(result.data) > 0:
            return float(result.data[0].get("value"))

        # No value found
        return None

    except Exception as e:
        logger.error(
            f"Error querying point value for {device_id}.{point}: {e!s}",
            extra={
                "device_id": device_id,
                "point": point,
                "site_id": site_id,
            },
        )
        raise
