"""Unified execution service for building control commands.

Single pipeline for all device writes in SENTINEL: write → verify → audit → return.

All execution paths (Tier 2 human approval, Tier 3 auto-execute, manual)
must call execute_command() rather than writing to device_manager directly.
This guarantees verification always runs and audit always writes on every path,
including failure paths.

Optimisation auto-execution is NOT routed here (disabled, see TODO-PHASE2
in api/optimization.py). Only advisory, supervised, and manual sources.

Phase 185 Wave 2 additions:
- SentinelWriteWhitelist gate: blocks writes to non-whitelisted equipment/points
- bacnet_priority: passed through to device_manager.write_device_value()
- previous_value: captured pre-write and returned for audit trail
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from app.database.repositories.audit_repository import AuditRepository
from app.services.cov_monitor_service import get_cov_monitor_service
from app.services.device_abstraction import device_manager
from app.services.sentinel_write_whitelist import get_sentinel_write_whitelist
from app.services.simbiot.bms_adapter import BmsConnectionConfig, BmsWriteRequest

logger = logging.getLogger(__name__)

# BACnet priority scale: lower number = higher precedence
# 1 = life safety, 2 = critical, 3 = manual operator, 5 = comfort override,
# 8 = scheduled setpoint (SENTINEL default), 13-16 =最低优先级
BACNET_PRIORITY_BY_CLASSIFICATION = {
    # LIFE_SAFETY always uses priority 1
    "LIFE_SAFETY": 1,
    # BESS dispatch uses priority 2 (power hardware)
    "BESS": 2,
    # STAGING (chiller/boiler/AHU staging) uses priority 3 (manual operator level)
    "STAGING": 3,
    # ON_OFF binary overrides use priority 5 (comfort override)
    "ON_OFF": 5,
    # SETPOINT, LIGHTING use priority 8 (scheduled/auto setpoint)
    "SETPOINT": 8,
    "LIGHTING": 8,
    # UNKNOWN conservative fallback = 8
    "UNKNOWN": 8,
}


async def execute_command(
    site_id: str,
    equipment_id: str,
    control_point: str,
    target_value: Any,
    source: str,
    correlation_id: str,
    decision_id: str | None = None,
    sentinel_tool=None,
    bacnet_priority: int | None = None,
) -> dict:
    """Execute a device write with mandatory verification and audit.

    This is the single execution entry point for all device writes.
    It enforces: whitelist gate → write → read-back verify → audit on every call,
    including failure cases.

    Phase 185 Wave 2: Added whitelist gate and bacnet_priority support.

    Args:
        site_id: Site the equipment belongs to.
        equipment_id: Equipment identifier (SENTINEL naming convention).
        control_point: Point/property name to write (e.g. 'setpoint').
        target_value: Value to write.
        source: Execution source — "advisory", "manual", or "optimization".
        correlation_id: End-to-end trace ID.
        decision_id: Optional PARASITE decision ID for audit linkage.
        sentinel_tool: Optional SentinelTool instance. Used to derive bacnet_priority
            when not explicitly supplied.
        bacnet_priority: BACnet priority (1-16, lower = higher priority).
            If None, derived from sentinel_tool.classification via
            BACNET_PRIORITY_BY_CLASSIFICATION. Defaults to 8.

    Returns:
        {
            "success": bool,
            "expected_value": <target_value>,
            "actual_value": float | None,
            "verified": bool,
            "error": str | None,
            "correlation_id": str,
            "previous_value": Any | None,      # pre-write device value
            "whitelist_passed": bool,           # whether whitelist gate passed
            "whitelist_reason": str,            # denial reason if blocked
            "bacnet_priority": int,              # priority used for write
        }
    """
    effective_decision_id = decision_id or str(uuid.uuid4())
    actual_value: Any = None
    verified = False
    success = False
    error: str | None = None
    previous_value: Any = None
    whitelist_passed = False
    whitelist_reason = ""
    execution_metadata: dict[str, Any] = {"write_path": "device_manager"}

    # --- Wave 2: Determine BACnet priority ---
    write_priority = bacnet_priority
    if write_priority is None and sentinel_tool is not None:
        classification = (
            sentinel_tool.classification.value
            if hasattr(sentinel_tool.classification, "value")
            else str(sentinel_tool.classification)
        )
        write_priority = BACNET_PRIORITY_BY_CLASSIFICATION.get(classification, 8)
    elif write_priority is None:
        write_priority = 8  # SENTINEL default

    # --- Wave 2: Whitelist gate ---
    whitelist = get_sentinel_write_whitelist()
    wl_result = whitelist.can_write(equipment_id, control_point)
    whitelist_passed = wl_result.allowed
    whitelist_reason = wl_result.reason

    if not whitelist_passed:
        error = f"WHITELIST_DENIED: {wl_result.reason}"
        logger.warning(
            f"execute_command whitelist blocked: equipment={equipment_id} "
            f"point={control_point} reason={wl_result.reason}"
        )
        # Audit the blocked attempt, then return
        _audit_execution(
            site_id=site_id,
            equipment_id=equipment_id,
            control_point=control_point,
            target_value=target_value,
            actual_value=None,
            source=source,
            correlation_id=correlation_id,
            decision_id=effective_decision_id,
            success=False,
            verified=False,
            error=error,
            previous_value=None,
            bacnet_priority=write_priority,
            whitelist_version=wl_result.whitelist_version,
        )
        return {
            "success": False,
            "expected_value": target_value,
            "actual_value": None,
            "verified": False,
            "error": error,
            "correlation_id": correlation_id,
            "previous_value": None,
            "whitelist_passed": False,
            "whitelist_reason": wl_result.reason,
            "bacnet_priority": write_priority,
        }

    # --- Read previous value before write (for audit trail) ---
    try:
        current = await device_manager.read_device_value(equipment_id, control_point)
        previous_value = current.value
    except Exception as e:
        logger.debug(f"Could not pre-read {equipment_id}.{control_point}: {e}")
        previous_value = None

    try:
        # Step 1: Write to device. Bridge-configured sites must use the site
        # adapter first; otherwise a local/sim device manager can report success
        # without the command ever reaching the site bridge.
        if _site_should_use_adapter_write(site_id):
            fallback = await _execute_site_adapter_write(
                site_id=site_id,
                equipment_id=equipment_id,
                control_point=control_point,
                target_value=target_value,
                priority=write_priority,
                source=source,
                correlation_id=correlation_id,
            )
            success = bool(fallback.get("success"))
            previous_value = fallback.get("previous_value", previous_value)
            actual_value = fallback.get("actual_value")
            verified = bool(fallback.get("verified", False))
            error = None if success else fallback.get("error")
            execution_metadata.update(
                {
                    "write_path": "site_adapter",
                    "adapter_id": fallback.get("adapter_id"),
                    "bridge_point_id": fallback.get("bridge_point_id"),
                    "bridge_write_response": fallback.get("write_response"),
                }
            )
            if not success:
                logger.error(
                    "execute_command site adapter write failed: equipment=%s point=%s error=%s",
                    equipment_id,
                    control_point,
                    error,
                )
        else:
            try:
                write_ok = await device_manager.write_device_value(
                    device_id=equipment_id,
                    point_name=control_point,
                    value=target_value,
                    priority=write_priority,
                )
                success = bool(write_ok)
                if not success:
                    error = f"Device write returned False for {equipment_id}.{control_point}"
            except Exception as exc:
                success = False
                error = f"Device write exception: {exc}"
                logger.error(
                    "execute_command device_manager write failed: equipment=%s point=%s error=%s",
                    equipment_id,
                    control_point,
                    exc,
                )

        # Step 2: Verify (always attempt, even on write failure, to capture actual state)
        if success and execution_metadata.get("write_path") != "site_adapter":
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
            previous_value=previous_value,
            bacnet_priority=write_priority,
            whitelist_version=wl_result.whitelist_version,
            execution_metadata=execution_metadata,
        )

    return {
        "success": success,
        "expected_value": target_value,
        "actual_value": actual_value,
        "verified": verified,
        "error": error,
        "correlation_id": correlation_id,
        "previous_value": previous_value,
        "whitelist_passed": whitelist_passed,
        "whitelist_reason": whitelist_reason,
        "bacnet_priority": write_priority,
        **execution_metadata,
    }


def _site_should_use_adapter_write(site_id: str) -> bool:
    """Return True when the site has an enabled write-capable bridge adapter."""
    if not site_id:
        return False
    try:
        from app.database.supabase_client import get_supabase_client

        result = (
            get_supabase_client()
            .table("site_adapter_config")
            .select("protocol,enabled,connection_config")
            .eq("site_id", site_id)
            .eq("enabled", True)
            .execute()
        )
        for row in result.data or []:
            protocol = str(row.get("protocol") or "").strip().lower()
            config = row.get("connection_config") or {}
            if protocol == "bridge" and config.get("supports_writes") is True and config.get("write_enabled") is True:
                return True
    except Exception as exc:
        logger.debug("Could not determine adapter write preference for %s: %s", site_id, exc)
    return False


async def _execute_site_adapter_write(
    *,
    site_id: str,
    equipment_id: str,
    control_point: str,
    target_value: Any,
    priority: int,
    source: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Fallback write path for SIMBIOT site adapters such as the HTTP bridge."""
    if not site_id:
        return {"success": False, "error": "No site_id provided for site adapter write"}

    try:
        from app.database.supabase_client import get_supabase_client
        from app.services.site_adapter_manager import SiteAdapterManager

        sb = get_supabase_client()
        site_row = sb.table("sites").select("id").eq("code", site_id).limit(1).execute()
        if not site_row.data:
            return {"success": False, "error": f"Site {site_id} not found"}
        site_uuid = site_row.data[0]["id"]

        mapping_row = (
            sb.table("point_asset_mappings")
            .select("bms_point_id,parameter_name,parameter_type,is_verified")
            .eq("site_id", site_uuid)
            .eq("extracted_asset_id", equipment_id)
            .eq("is_verified", True)
            .execute()
        )
        bridge_point_id = None
        requested = str(control_point or "").strip().lower()
        for mapping in mapping_row.data or []:
            parameter_name = str(mapping.get("parameter_name") or "").strip().lower()
            bms_point_id = str(mapping.get("bms_point_id") or "").strip()
            suffix = bms_point_id.rsplit(".", 1)[-1].lower() if "." in bms_point_id else bms_point_id.lower()
            parameter_type = str(mapping.get("parameter_type") or "").lower()
            is_writable = (
                parameter_type in {"command", "setpoint", "writable"}
                or parameter_type.startswith(("command:", "setpoint:", "writable:"))
                or "analogoutput" in parameter_type
                or "binaryoutput" in parameter_type
                or "multistateoutput" in parameter_type
            )
            if is_writable and requested in {parameter_name, suffix}:
                bridge_point_id = bms_point_id
                break
        if not bridge_point_id:
            return {"success": False, "error": f"No verified writable bridge point for {equipment_id}.{control_point}"}

        adapters = SiteAdapterManager(sb).get_adapters_for_site(site_id)
        writable_adapters = [adapter for adapter in adapters if adapter.capabilities.supports_writes]
        if not writable_adapters:
            return {"success": False, "error": f"No write-capable adapter enabled for {site_id}"}

        adapter = writable_adapters[0]
        connection_status = await adapter.connect(BmsConnectionConfig(site_id=site_id, source_type=adapter.adapter_id))
        if not connection_status.connected:
            return {
                "success": False,
                "adapter_id": adapter.adapter_id,
                "bridge_point_id": bridge_point_id,
                "error": f"Bridge adapter connection failed: {connection_status.message or connection_status.status}",
            }

        previous_value = None
        try:
            current = await adapter.read_point(equipment_id, bridge_point_id)
            previous_value = current.value
        except Exception as exc:
            logger.debug("Could not pre-read via site adapter %s.%s: %s", equipment_id, bridge_point_id, exc)

        success = await adapter.write_point(
            BmsWriteRequest(
                device_id=equipment_id,
                point_id=bridge_point_id,
                value=target_value,
                priority=priority,
                user=source,
                metadata={"correlation_id": correlation_id, "sentinel_point": control_point},
            )
        )
        write_response = getattr(adapter, "last_write_response", None)
        actual_value = None
        verified = False
        if success:
            try:
                current = await adapter.read_point(equipment_id, bridge_point_id)
                actual_value = current.value
                if isinstance(target_value, (int, float)) and isinstance(actual_value, (int, float)):
                    tolerance = abs(float(target_value) * 0.05) if float(target_value) != 0 else 0.5
                    verified = abs(float(actual_value) - float(target_value)) <= tolerance
                else:
                    verified = actual_value == target_value
            except Exception as exc:
                logger.warning("Could not verify bridge write %s.%s: %s", equipment_id, bridge_point_id, exc)

        return {
            "success": bool(success),
            "adapter_id": adapter.adapter_id,
            "bridge_point_id": bridge_point_id,
            "write_response": write_response,
            "previous_value": previous_value,
            "actual_value": actual_value,
            "verified": verified,
            "error": None if success else f"Bridge adapter write returned False for {bridge_point_id}",
        }
    except Exception as exc:
        logger.error("Site adapter write failed for %s.%s: %s", equipment_id, control_point, exc)
        return {"success": False, "error": str(exc)}


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
    previous_value: Any = None,
    bacnet_priority: int = 8,
    whitelist_version: str = "",
    execution_metadata: dict[str, Any] | None = None,
) -> None:
    """Write a device-control audit record synchronously.

    Uses AuditRepository.log_device_control() which writes to the audit_log table.
    This is a fire-and-forget sync call; errors are logged but never propagate
    (audit failure must not mask execution failure).
    """
    try:
        audit_repo = AuditRepository()
        result_status = "SUCCESS" if success else "FAILED"
        device_uuid = None
        try:
            from uuid import UUID

            UUID(str(equipment_id))
            device_uuid = str(equipment_id)
        except ValueError:
            try:
                from app.database.supabase_client import get_supabase_client

                row = get_supabase_client().table("equipment").select("id").eq("code", equipment_id).limit(1).execute()
                if row.data:
                    device_uuid = row.data[0].get("id")
            except Exception as lookup_exc:
                logger.debug("Could not resolve equipment UUID for audit %s: %s", equipment_id, lookup_exc)
        audit_repo.log_device_control(
            device_id=device_uuid,
            point_name=control_point,
            old_value=previous_value,
            new_value=target_value,
            user_name=source,
            result=result_status,
            error_message=error,
            correlation_id=correlation_id,
            metadata={
                "action_type": "execution",
                "source": source,
                "site_id": site_id,
                "equipment_code": equipment_id,
                "decision_id": decision_id,
                "actual_value": actual_value,
                "verified": verified,
                "timestamp": datetime.utcnow().isoformat(),
                "bacnet_priority": bacnet_priority,
                "whitelist_version": whitelist_version,
                **(execution_metadata or {}),
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
