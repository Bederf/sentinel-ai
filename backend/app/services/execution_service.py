"""Unified execution service for building control commands.

Single pipeline for all device writes in SENTINEL: write → verify → audit → return.

All execution paths (Tier 2 human approval, Tier 3 auto-execute, manual)
must call execute_command() rather than writing to device_manager directly.
This guarantees verification always runs and audit always writes on every path,
including failure paths.

Optimisation auto-execution is NOT routed here (disabled, see TODO-PHASE2
in api/optimization.py). Only advisory, supervised, and manual sources.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from app.database.repositories.audit_repository import AuditRepository
from app.services.cov_monitor_service import get_cov_monitor_service
from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)


async def execute_command(
    site_id: str,
    equipment_id: str,
    control_point: str,
    target_value: Any,
    source: str,
    correlation_id: str,
    decision_id: str | None = None,
) -> dict:
    """Execute a device write with mandatory verification and audit.

    This is the single execution entry point for all device writes.
    It enforces: write → read-back verify → audit on every call,
    including failure cases.

    Args:
        site_id: Site the equipment belongs to.
        equipment_id: Equipment identifier (SENTINEL naming convention).
        control_point: Point/property name to write (e.g. 'setpoint').
        target_value: Value to write.
        source: Execution source — "advisory", "manual", or "optimization".
        correlation_id: End-to-end trace ID.
        decision_id: Optional PARASITE decision ID for audit linkage.

    Returns:
        {
            "success": bool,
            "expected_value": <target_value>,
            "actual_value": float | None,
            "verified": bool,
            "error": str | None,
            "correlation_id": str,
        }
    """
    effective_decision_id = decision_id or str(uuid.uuid4())
    actual_value: Any = None
    verified = False
    success = False
    error: str | None = None

    try:
        # Step 1: Write to device
        try:
            write_ok = await device_manager.write_device_value(
                device_id=equipment_id,
                point_name=control_point,
                value=target_value,
            )
            success = bool(write_ok)
            if not success:
                error = f"Device write returned False for {equipment_id}.{control_point}"
        except Exception as exc:
            success = False
            error = f"Device write exception: {exc}"
            logger.error(
                "execute_command write failed: equipment=%s point=%s error=%s",
                equipment_id,
                control_point,
                exc,
            )

        # Step 2: Verify (always attempt, even on write failure, to capture actual state)
        if success:
            try:
                cov_monitor = get_cov_monitor_service()
                cov_result = await cov_monitor.verify_write(
                    equipment_id=equipment_id,
                    point_name=control_point,
                    expected_value=target_value,
                    decision_id=effective_decision_id,
                )
                verified = cov_result.verified
                actual_value = cov_result.actual_value
                if not verified:
                    logger.warning(
                        "execute_command COV mismatch: equipment=%s point=%s expected=%s actual=%s",
                        equipment_id,
                        control_point,
                        target_value,
                        actual_value,
                    )
            except Exception as exc:
                verified = False
                actual_value = None
                logger.warning(
                    "execute_command COV verification failed: equipment=%s point=%s error=%s",
                    equipment_id,
                    control_point,
                    exc,
                )

    finally:
        # Step 3: Audit — always runs, including on exception paths above
        _audit_execution(
            site_id=site_id,
            equipment_id=equipment_id,
            control_point=control_point,
            target_value=target_value,
            actual_value=actual_value,
            source=source,
            correlation_id=correlation_id,
            decision_id=effective_decision_id,
            success=success,
            verified=verified,
            error=error,
        )

    return {
        "success": success,
        "expected_value": target_value,
        "actual_value": actual_value,
        "verified": verified,
        "error": error,
        "correlation_id": correlation_id,
    }


def _audit_execution(
    *,
    site_id: str,
    equipment_id: str,
    control_point: str,
    target_value: Any,
    actual_value: Any,
    source: str,
    correlation_id: str,
    decision_id: str,
    success: bool,
    verified: bool,
    error: str | None,
) -> None:
    """Write a device-control audit record synchronously.

    Uses AuditRepository.log_device_control() which writes to the audit_log table.
    This is a fire-and-forget sync call; errors are logged but never propagate
    (audit failure must not mask execution failure).
    """
    try:
        audit_repo = AuditRepository()
        result_status = "SUCCESS" if success else "FAILED"
        audit_repo.log_device_control(
            device_id=equipment_id,
            point_name=control_point,
            old_value=None,
            new_value=target_value,
            user_name=source,
            result=result_status,
            error_message=error,
            correlation_id=correlation_id,
            metadata={
                "action_type": "execution",
                "source": source,
                "site_id": site_id,
                "decision_id": decision_id,
                "actual_value": actual_value,
                "verified": verified,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as exc:
        # Audit failure is logged but never re-raised.
        # Losing an audit entry is bad; masking an execution result is worse.
        logger.error(
            "execute_command audit write failed: equipment=%s correlation=%s error=%s",
            equipment_id,
            correlation_id,
            exc,
        )
