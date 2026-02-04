"""Remote Command Execution Service.

Provides safe remote command execution with:
- Authorization checks (4-level model)
- Safety guardrails (hardcoded, non-configurable)
- Auto-expiring overrides (setpoint 4h, schedule 8h, door 5min)
- Rollback capability (revert to pre-command state)
- Rate limiting (10 commands/user/hour)

Phase 59-02: Remote Operations
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.models.remote_ops import AuthorizationLevel, COMMAND_AUTHORIZATION
from app.services.auth_service import get_authorization_service
from app.services.device_abstraction import device_manager
from app.services.audit_logger import AuditLogger
from app.models.audit_log import AuditActionType, AuditResultType

logger = logging.getLogger(__name__)


class RemoteCommandService:
    """Singleton service for executing remote commands with safety guardrails.

    Safety guardrails are hardcoded and non-configurable to prevent
    accidental or malicious override of safety limits.
    """

    _instance: Optional["RemoteCommandService"] = None

    # Hardcoded safety guardrails -- NOT configurable
    _safety_guardrails = {
        "max_setpoint_delta_celsius": 3.0,
        "absolute_temp_min_celsius": 16.0,
        "absolute_temp_max_celsius": 28.0,
        "life_safety_device_types": ["fire_safety"],
        "setpoint_override_hours": 4,
        "schedule_override_hours": 8,
        "door_unlock_minutes": 5,
        "max_commands_per_user_per_hour": 10,
        "rate_limit_warning_threshold": 8,
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._active_overrides: Dict[str, Dict[str, Any]] = {}
        self._command_history: List[Dict[str, Any]] = []
        self._rate_limit_counters: Dict[str, List[datetime]] = {}
        self._audit_logger = AuditLogger()
        self._auth_service = get_authorization_service()
        self._initialized = True
        logger.info("RemoteCommandService initialized with hardcoded safety guardrails")

    # ------------------------------------------------------------------ #
    #  Core command execution
    # ------------------------------------------------------------------ #

    async def execute_remote_command(
        self,
        user_id: str,
        user_role: str,
        device_id: str,
        command_type: str,
        point: Optional[str] = None,
        value: Optional[Any] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Execute a remote command with full safety validation.

        Steps:
        1. Check authorization level
        2. Check rate limiting
        3. Validate command against safety guardrails
        4. Record pre-command state for rollback
        5. Execute via device_manager
        6. Log to audit
        7. Schedule auto-expiry if override type
        8. Return result with rollback info

        Returns:
            Dict with success, command_id, previous_value, new_value,
            expires_at, rollback_available, and safety_warnings.
        """
        command_id = str(uuid.uuid4())
        safety_warnings: List[str] = []

        # 1. Authorization check
        required_level = COMMAND_AUTHORIZATION.get(
            command_type, AuthorizationLevel.ENGINEER
        )
        if not self._auth_service.check_authorization(user_role, required_level):
            self._log_command(
                command_id, user_id, user_role, device_id, command_type,
                point, value, reason, success=False,
                error="Insufficient authorization",
            )
            return {
                "success": False,
                "command_id": command_id,
                "error": f"Insufficient authorization. Requires {required_level.name}, "
                         f"user has {self._auth_service.get_user_authorization_level(user_role).name}",
                "safety_warnings": [],
            }

        # 2. Rate limiting
        rate_result = self._check_rate_limit(user_id)
        if rate_result["blocked"]:
            self._log_command(
                command_id, user_id, user_role, device_id, command_type,
                point, value, reason, success=False,
                error="Rate limit exceeded",
            )
            return {
                "success": False,
                "command_id": command_id,
                "error": f"Rate limit exceeded: {rate_result['message']}",
                "safety_warnings": [],
            }
        if rate_result.get("warning"):
            safety_warnings.append(rate_result["warning"])

        # 3. Command-specific safety validation
        validation = await self._validate_command(
            device_id, command_type, point, value, user_role
        )
        if not validation["allowed"]:
            self._log_command(
                command_id, user_id, user_role, device_id, command_type,
                point, value, reason, success=False,
                error=validation["error"],
            )
            return {
                "success": False,
                "command_id": command_id,
                "error": validation["error"],
                "safety_warnings": validation.get("warnings", []),
            }
        safety_warnings.extend(validation.get("warnings", []))

        # 4. Record pre-command state for rollback
        previous_value = None
        if point:
            try:
                device_value = await device_manager.read_device_value(device_id, point)
                previous_value = device_value.value
            except Exception as e:
                logger.warning(f"Could not read current value for rollback: {e}")

        # 5. Execute the command
        try:
            if command_type == "status_check":
                # Status checks don't write anything
                result_data = await self._execute_status_check(device_id)
                self._log_command(
                    command_id, user_id, user_role, device_id, command_type,
                    point, value, reason, success=True,
                )
                return {
                    "success": True,
                    "command_id": command_id,
                    "data": result_data,
                    "safety_warnings": safety_warnings,
                    "rollback_available": False,
                }

            # For write commands, execute through device_manager
            if point and value is not None:
                success = await device_manager.write_device_value(
                    device_id, point, value, priority=8, user=user_id
                )
            else:
                success = True  # Commands without point/value (e.g. fault_reset stub)

            if not success:
                self._log_command(
                    command_id, user_id, user_role, device_id, command_type,
                    point, value, reason, success=False,
                    error="Device write failed",
                )
                return {
                    "success": False,
                    "command_id": command_id,
                    "error": "Device write failed",
                    "safety_warnings": safety_warnings,
                }

        except ValueError as e:
            # Safety engine blocks will raise ValueError
            self._log_command(
                command_id, user_id, user_role, device_id, command_type,
                point, value, reason, success=False, error=str(e),
            )
            return {
                "success": False,
                "command_id": command_id,
                "error": str(e),
                "safety_warnings": safety_warnings,
            }
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            self._log_command(
                command_id, user_id, user_role, device_id, command_type,
                point, value, reason, success=False, error=str(e),
            )
            return {
                "success": False,
                "command_id": command_id,
                "error": f"Execution error: {e}",
                "safety_warnings": safety_warnings,
            }

        # 6. Audit logging (source=remote_command)
        self._audit_logger.log_control_action(
            device_id=device_id,
            point_name=point or command_type,
            user=user_id,
            old_value=previous_value,
            new_value=value,
            result=AuditResultType.SUCCESS,
            metadata={
                "source": "remote_command",
                "command_type": command_type,
                "command_id": command_id,
                "reason": reason,
                "user_role": user_role,
            },
        )

        # 7. Schedule auto-expiry for override types
        expires_at = None
        if command_type in ("setpoint_adjust", "schedule_override", "door_unlock") and point:
            expires_at = self._schedule_override(
                command_id, device_id, point, previous_value, value, user_id, command_type
            )

        # 8. Record in history
        self._log_command(
            command_id, user_id, user_role, device_id, command_type,
            point, value, reason, success=True,
            previous_value=previous_value,
            expires_at=expires_at,
        )

        return {
            "success": True,
            "command_id": command_id,
            "previous_value": previous_value,
            "new_value": value,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "rollback_available": previous_value is not None,
            "safety_warnings": safety_warnings,
        }

    # ------------------------------------------------------------------ #
    #  Override management
    # ------------------------------------------------------------------ #

    def _schedule_override(
        self,
        command_id: str,
        device_id: str,
        point: str,
        original_value: Any,
        new_value: Any,
        user_id: str,
        command_type: str,
    ) -> datetime:
        """Register an auto-expiring override and return expiry time."""
        guardrails = self._safety_guardrails

        if command_type == "setpoint_adjust":
            duration = timedelta(hours=guardrails["setpoint_override_hours"])
        elif command_type == "schedule_override":
            duration = timedelta(hours=guardrails["schedule_override_hours"])
        elif command_type == "door_unlock":
            duration = timedelta(minutes=guardrails["door_unlock_minutes"])
        else:
            duration = timedelta(hours=guardrails["setpoint_override_hours"])

        expires_at = datetime.now() + duration

        self._active_overrides[command_id] = {
            "command_id": command_id,
            "device_id": device_id,
            "point": point,
            "original_value": original_value,
            "new_value": new_value,
            "user_id": user_id,
            "command_type": command_type,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        logger.info(
            f"Override {command_id} scheduled: {device_id}/{point} "
            f"reverts at {expires_at.isoformat()}"
        )
        return expires_at

    async def check_expired_overrides(self) -> List[Dict[str, Any]]:
        """Check and revert expired overrides.

        Called periodically (e.g., every minute) to revert overrides
        that have passed their expiry time.

        Returns:
            List of override dicts that were reverted.
        """
        now = datetime.now()
        reverted: List[Dict[str, Any]] = []
        expired_ids: List[str] = []

        for cmd_id, override in self._active_overrides.items():
            expires_at = datetime.fromisoformat(override["expires_at"])
            if now >= expires_at:
                expired_ids.append(cmd_id)
                # Attempt to revert
                try:
                    if override["original_value"] is not None:
                        await device_manager.write_device_value(
                            override["device_id"],
                            override["point"],
                            override["original_value"],
                            priority=8,
                            user="system_auto_revert",
                        )
                    self._audit_logger.log_control_action(
                        device_id=override["device_id"],
                        point_name=override["point"],
                        user="system_auto_revert",
                        old_value=override["new_value"],
                        new_value=override["original_value"],
                        result=AuditResultType.SUCCESS,
                        metadata={
                            "source": "remote_command",
                            "action": "auto_revert",
                            "command_id": cmd_id,
                            "reason": "Override expired",
                        },
                    )
                    override["reverted"] = True
                    reverted.append(override)
                    logger.info(
                        f"Auto-reverted override {cmd_id}: "
                        f"{override['device_id']}/{override['point']} "
                        f"→ {override['original_value']}"
                    )
                except Exception as e:
                    logger.error(f"Failed to auto-revert override {cmd_id}: {e}")
                    override["reverted"] = False
                    override["revert_error"] = str(e)
                    reverted.append(override)

        # Remove expired overrides from active dict
        for cmd_id in expired_ids:
            del self._active_overrides[cmd_id]

        return reverted

    async def rollback_command(
        self, command_id: str, user_id: str, user_role: str
    ) -> Dict[str, Any]:
        """Manually revert a command to its pre-command state.

        Args:
            command_id: The command to rollback.
            user_id: The user requesting the rollback.
            user_role: The user's role (must be owner or ENGINEER).

        Returns:
            Dict with success, device_id, point, restored_value.
        """
        override = self._active_overrides.get(command_id)
        if not override:
            # Check history for non-override commands
            history_entry = next(
                (h for h in self._command_history if h["command_id"] == command_id),
                None,
            )
            if not history_entry:
                return {
                    "success": False,
                    "error": f"Command {command_id} not found",
                }
            if history_entry.get("previous_value") is None:
                return {
                    "success": False,
                    "error": "No previous value recorded for rollback",
                }
            # Build override-like dict from history
            override = {
                "command_id": command_id,
                "device_id": history_entry["device_id"],
                "point": history_entry.get("point"),
                "original_value": history_entry["previous_value"],
                "new_value": history_entry.get("value"),
                "user_id": history_entry["user_id"],
            }

        # Authorization: must be command owner or ENGINEER
        if override["user_id"] != user_id:
            if not self._auth_service.check_authorization(
                user_role, AuthorizationLevel.ENGINEER
            ):
                return {
                    "success": False,
                    "error": "Only the command owner or an ENGINEER can rollback",
                }

        if override.get("original_value") is None:
            return {
                "success": False,
                "error": "No previous value available for rollback",
            }

        try:
            await device_manager.write_device_value(
                override["device_id"],
                override["point"],
                override["original_value"],
                priority=8,
                user=user_id,
            )

            self._audit_logger.log_control_action(
                device_id=override["device_id"],
                point_name=override["point"],
                user=user_id,
                old_value=override["new_value"],
                new_value=override["original_value"],
                result=AuditResultType.SUCCESS,
                metadata={
                    "source": "remote_command",
                    "action": "manual_rollback",
                    "command_id": command_id,
                    "user_role": user_role,
                },
            )

            # Remove from active overrides if present
            self._active_overrides.pop(command_id, None)

            logger.info(
                f"Rollback {command_id}: {override['device_id']}/{override['point']} "
                f"→ {override['original_value']} by {user_id}"
            )

            return {
                "success": True,
                "device_id": override["device_id"],
                "point": override["point"],
                "restored_value": override["original_value"],
            }

        except Exception as e:
            logger.error(f"Rollback failed for {command_id}: {e}")
            return {
                "success": False,
                "error": f"Rollback failed: {e}",
            }

    def get_active_overrides(
        self, site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List active overrides, optionally filtered by site_id.

        Args:
            site_id: Optional site filter (matches against device_id prefix).

        Returns:
            List of active override dicts.
        """
        overrides = list(self._active_overrides.values())
        if site_id:
            overrides = [
                o for o in overrides
                if o["device_id"].startswith(site_id.replace("site-", "S").upper())
                or site_id in o["device_id"]
            ]
        return overrides

    # ------------------------------------------------------------------ #
    #  Command history
    # ------------------------------------------------------------------ #

    def get_command_history(
        self,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent command history with optional filters.

        Args:
            user_id: Filter by user.
            device_id: Filter by device.
            limit: Max results (default 20).

        Returns:
            List of command history entries, newest first.
        """
        history = self._command_history
        if user_id:
            history = [h for h in history if h["user_id"] == user_id]
        if device_id:
            history = [h for h in history if h["device_id"] == device_id]
        # newest first
        return list(reversed(history[-limit:]))

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    async def _validate_command(
        self,
        device_id: str,
        command_type: str,
        point: Optional[str],
        value: Optional[Any],
        user_role: str,
    ) -> Dict[str, Any]:
        """Validate command against hardcoded safety guardrails.

        Returns:
            Dict with allowed (bool), error (str), warnings (list).
        """
        guardrails = self._safety_guardrails
        warnings: List[str] = []

        # -- setpoint_adjust guardrails --
        if command_type == "setpoint_adjust" and point and value is not None:
            try:
                new_val = float(value)
            except (TypeError, ValueError):
                return {"allowed": False, "error": "Setpoint value must be numeric", "warnings": []}

            # Absolute range check
            if new_val < guardrails["absolute_temp_min_celsius"] or new_val > guardrails["absolute_temp_max_celsius"]:
                return {
                    "allowed": False,
                    "error": (
                        f"Setpoint {new_val}°C outside absolute safe range "
                        f"({guardrails['absolute_temp_min_celsius']}-"
                        f"{guardrails['absolute_temp_max_celsius']}°C)"
                    ),
                    "warnings": [],
                }

            # Delta from current value check
            try:
                current = await device_manager.read_device_value(device_id, point)
                current_val = float(current.value)
                delta = abs(new_val - current_val)
                if delta > guardrails["max_setpoint_delta_celsius"]:
                    return {
                        "allowed": False,
                        "error": (
                            f"Setpoint change of {delta:.1f}°C exceeds maximum "
                            f"allowed delta of ±{guardrails['max_setpoint_delta_celsius']}°C "
                            f"from current value {current_val}°C"
                        ),
                        "warnings": [],
                    }
            except Exception as e:
                warnings.append(f"Could not verify delta from current value: {e}")

        # -- equipment_start_stop guardrails --
        if command_type == "equipment_start_stop":
            device = await device_manager.get_device(device_id)
            if device and device.device_type.value in guardrails["life_safety_device_types"]:
                return {
                    "allowed": False,
                    "error": (
                        f"Remote start/stop blocked for life-safety device "
                        f"type '{device.device_type.value}'"
                    ),
                    "warnings": [],
                }

        # -- fire_panel_reset guardrails --
        if command_type == "fire_panel_reset":
            if not self._auth_service.check_authorization(
                user_role, AuthorizationLevel.ENGINEER
            ):
                return {
                    "allowed": False,
                    "error": "Fire panel reset requires ENGINEER level authorization",
                    "warnings": [],
                }
            warnings.append("ALARM: Fire panel reset is a critical operation - logged at ALARM level")
            # Log at ALARM level
            self._audit_logger.log_system_event(
                event_type="fire_panel_reset_attempt",
                user=user_role,
                result=AuditResultType.WARNING,
                metadata={
                    "device_id": device_id,
                    "severity": "ALARM",
                    "command_type": command_type,
                },
            )

        # -- door_unlock guardrails --
        if command_type == "door_unlock":
            if not self._auth_service.check_authorization(
                user_role, AuthorizationLevel.OPERATOR
            ):
                return {
                    "allowed": False,
                    "error": "Door unlock requires at least OPERATOR level",
                    "warnings": [],
                }
            warnings.append(
                f"Door will auto-lock after {guardrails['door_unlock_minutes']} minutes"
            )

        return {"allowed": True, "error": None, "warnings": warnings}

    def _check_rate_limit(self, user_id: str) -> Dict[str, Any]:
        """Check in-memory rate limiting for a user.

        Returns:
            Dict with blocked (bool), message (str), warning (str|None).
        """
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        guardrails = self._safety_guardrails

        # Clean old entries
        if user_id in self._rate_limit_counters:
            self._rate_limit_counters[user_id] = [
                ts for ts in self._rate_limit_counters[user_id] if ts > one_hour_ago
            ]
        else:
            self._rate_limit_counters[user_id] = []

        count = len(self._rate_limit_counters[user_id])

        # Block at max
        if count >= guardrails["max_commands_per_user_per_hour"]:
            return {
                "blocked": True,
                "message": (
                    f"Maximum {guardrails['max_commands_per_user_per_hour']} "
                    f"commands per hour exceeded ({count} in last hour)"
                ),
                "warning": None,
            }

        # Warning at threshold
        warning = None
        if count >= guardrails["rate_limit_warning_threshold"]:
            remaining = guardrails["max_commands_per_user_per_hour"] - count
            warning = f"Rate limit warning: {remaining} commands remaining this hour"

        # Record this command
        self._rate_limit_counters[user_id].append(now)

        return {"blocked": False, "message": "OK", "warning": warning}

    async def _execute_status_check(self, device_id: str) -> Dict[str, Any]:
        """Execute a read-only status check on a device."""
        device = await device_manager.get_device(device_id)
        if not device:
            return {"error": f"Device {device_id} not found"}

        adapter = await device_manager.get_adapter(device_id)
        points_data = {}
        if adapter:
            try:
                points = await adapter.get_points()
                for name, pt in points.items():
                    try:
                        val = await adapter.read_value(name)
                        points_data[name] = {
                            "value": val.value,
                            "unit": val.unit,
                            "quality": val.quality,
                        }
                    except Exception:
                        points_data[name] = {"value": pt.default_value, "quality": "stale"}
            except Exception as e:
                logger.warning(f"Could not read points for status check: {e}")

        return {
            "device_id": device_id,
            "device_name": device.name,
            "status": device.status.value if device.status else "unknown",
            "device_type": device.device_type.value,
            "points": points_data,
        }

    def _log_command(
        self,
        command_id: str,
        user_id: str,
        user_role: str,
        device_id: str,
        command_type: str,
        point: Optional[str],
        value: Optional[Any],
        reason: str,
        success: bool,
        error: Optional[str] = None,
        previous_value: Optional[Any] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        """Record command in in-memory history."""
        self._command_history.append({
            "command_id": command_id,
            "user_id": user_id,
            "user_role": user_role,
            "device_id": device_id,
            "command_type": command_type,
            "point": point,
            "value": value,
            "reason": reason,
            "success": success,
            "error": error,
            "previous_value": previous_value,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "executed_at": datetime.now().isoformat(),
        })
        # Cap history size
        if len(self._command_history) > 500:
            self._command_history = self._command_history[-500:]


def get_remote_command_service() -> RemoteCommandService:
    """Factory function returning the singleton RemoteCommandService."""
    return RemoteCommandService()
