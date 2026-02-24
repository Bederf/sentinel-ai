"""Modbus BESS Writer — Async TCP writer for Huawei LUNA2000 charge/discharge setpoints.

Register map (from solar_connector_huawei.py):
  37001 (i32, scale 1000): charge_power_kw
  37003 (i32, scale 1000): discharge_power_kw

Write protocol:
  1. BESSDispatchEngine validates constraints
  2. AEGIS gate check (aegis_bess_writer_enabled)
  3. Modbus TCP write to register
  4. Read-back verification (write-then-read)
  5. JSONL audit log

Safety:
  - AEGIS gate must be open (aegis_bess_writer_enabled=True)
  - Constraint validation via BESSDispatchEngine
  - Read-back verification (optional, default on)
  - 5-minute watchdog (sends idle/0kW if no command received)
  - Connection/write timeouts

DEMO_MODE: logs commands, returns success, never opens TCP.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.config.settings import settings
from app.services.bess_dispatch_engine import (
    BESSState,
    DispatchCommand,
    get_bess_dispatch_engine,
)

logger = logging.getLogger(__name__)

# Audit log path
AUDIT_DIR = Path(__file__).parent.parent / "data" / "modbus_audit"

# Huawei LUNA2000 register addresses
REGISTER_CHARGE_POWER = 37001  # i32, scale 1000 (kW -> W)
REGISTER_DISCHARGE_POWER = 37003  # i32, scale 1000 (kW -> W)
REGISTER_SCALE = 1000  # kW to register value


@dataclass
class WriteResult:
    """Result of a Modbus write operation.

    Audit-friendly: every write is traceable with correlation_id,
    requested vs clamped vs actual power, timestamps, and reason.
    """

    success: bool
    register: int
    value_kw: float  # Power after Sprint 0 clamping
    register_value: int  # Scaled value written to register
    verified: bool = False  # True if read-back matched
    aegis_blocked: bool = False
    demo_mode: bool = False
    error: Optional[str] = None
    timestamp: str = ""
    write_latency_ms: float = 0.0
    # Audit-friendly fields (Sprint 0 hardening)
    correlation_id: str = ""  # Unique ID for this write operation
    requested_kw: float = 0.0  # Original requested power (before clamping)
    clamped_kw: float = 0.0  # Power after Sprint 0 hard limit
    reason: str = ""  # Why this command was issued
    who: str = "sentinel"  # Who initiated (sentinel / operator / test)
    end_timestamp: str = ""  # When the write completed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "register": self.register,
            "value_kw": round(self.value_kw, 2),
            "register_value": self.register_value,
            "verified": self.verified,
            "aegis_blocked": self.aegis_blocked,
            "demo_mode": self.demo_mode,
            "error": self.error,
            "timestamp": self.timestamp,
            "write_latency_ms": round(self.write_latency_ms, 2),
            "correlation_id": self.correlation_id,
            "requested_kw": round(self.requested_kw, 2),
            "clamped_kw": round(self.clamped_kw, 2),
            "reason": self.reason,
            "who": self.who,
            "end_timestamp": self.end_timestamp,
        }


class ModbusBESSWriter:
    """Async Modbus TCP writer for Huawei LUNA2000.

    Writes charge/discharge setpoints to LUNA2000 registers via Modbus TCP.
    All writes are gated by AEGIS (aegis_bess_writer_enabled setting).

    In DEMO_MODE or when modbus_bess_ip is empty: logs commands, returns
    success without opening any TCP connection.
    """

    WATCHDOG_TIMEOUT_S = 300  # 5 minutes — send idle if no command received

    def __init__(self):
        self._client = None
        self._last_command_time: float = 0.0
        self._write_history: List[WriteResult] = []
        self._connected = False

    @property
    def _is_demo(self) -> bool:
        """True when no real Modbus TCP target is configured."""
        return settings.demo_mode or not settings.modbus_bess_ip

    @property
    def _aegis_enabled(self) -> bool:
        """True when AEGIS allows hardware writes."""
        return getattr(settings, "aegis_bess_writer_enabled", False)

    async def _ensure_connected(self) -> bool:
        """Establish Modbus TCP connection if needed.

        Returns True if connected (or demo mode), False on failure.
        """
        if self._is_demo:
            return True

        if self._connected and self._client is not None:
            return True

        try:
            from pymodbus.client import AsyncModbusTcpClient

            self._client = AsyncModbusTcpClient(
                host=settings.modbus_bess_ip,
                port=settings.modbus_bess_port,
                timeout=settings.modbus_bess_timeout_s,
            )
            connected = await self._client.connect()
            self._connected = connected
            if connected:
                logger.info(
                    "Modbus TCP connected to %s:%d",
                    settings.modbus_bess_ip,
                    settings.modbus_bess_port,
                )
            else:
                logger.error(
                    "Modbus TCP connection failed to %s:%d",
                    settings.modbus_bess_ip,
                    settings.modbus_bess_port,
                )
            return connected
        except ImportError:
            logger.error("pymodbus not installed — cannot write to BESS")
            return False
        except Exception as e:
            logger.error("Modbus TCP connection error: %s", e)
            self._connected = False
            return False

    async def disconnect(self):
        """Close the Modbus TCP connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._connected = False

    async def write_charge_setpoint(
        self,
        power_kw: float,
        reason: str = "",
        who: str = "sentinel",
    ) -> WriteResult:
        """Write charge power setpoint to LUNA2000 register 37001.

        Args:
            power_kw: Charge power in kW (positive value)
            reason: Why this command was issued
            who: Who initiated (dispatch_scheduler / operator / test_suite / sentinel)

        Returns:
            WriteResult with success/failure details
        """
        return await self._write_register(
            REGISTER_CHARGE_POWER,
            abs(power_kw),
            "charge",
            reason=reason,
            who=who,
        )

    async def write_discharge_setpoint(
        self,
        power_kw: float,
        reason: str = "",
        who: str = "sentinel",
    ) -> WriteResult:
        """Write discharge power setpoint to LUNA2000 register 37003.

        Args:
            power_kw: Discharge power in kW (positive value)
            reason: Why this command was issued
            who: Who initiated (dispatch_scheduler / operator / test_suite / sentinel)

        Returns:
            WriteResult with success/failure details
        """
        return await self._write_register(
            REGISTER_DISCHARGE_POWER,
            abs(power_kw),
            "discharge",
            reason=reason,
            who=who,
        )

    async def write_idle(self, reason: str = "", who: str = "sentinel") -> WriteResult:
        """Write idle (0 kW) to both charge and discharge registers.

        Used by watchdog timer and manual idle commands.
        """
        charge_result = await self._write_register(
            REGISTER_CHARGE_POWER,
            0.0,
            "idle",
            reason=reason,
            who=who,
        )
        await self._write_register(
            REGISTER_DISCHARGE_POWER,
            0.0,
            "idle",
            reason=reason,
            who=who,
        )
        return charge_result

    async def execute_dispatch_command(
        self,
        command: DispatchCommand,
        who: str = "sentinel",
    ) -> WriteResult:
        """Execute a validated DispatchCommand by writing to the appropriate register.

        Args:
            command: Pre-validated DispatchCommand from BESSDispatchEngine
            who: Who initiated this dispatch

        Returns:
            WriteResult with success/failure details
        """
        if not command.success:
            return WriteResult(
                success=False,
                register=0,
                value_kw=0.0,
                register_value=0,
                error=f"Command was blocked: {command.error_message}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                who=who,
                reason=command.reason,
            )

        if command.action == "charge":
            result = await self.write_charge_setpoint(
                command.actual_power_kw,
                reason=command.reason,
                who=who,
            )
        elif command.action == "discharge":
            result = await self.write_discharge_setpoint(
                command.actual_power_kw,
                reason=command.reason,
                who=who,
            )
        else:
            result = await self.write_idle(reason=command.reason, who=who)

        self._last_command_time = time.monotonic()
        return result

    async def _write_register(
        self,
        register: int,
        power_kw: float,
        label: str,
        reason: str = "",
        who: str = "sentinel",
    ) -> WriteResult:
        """Core register write with AEGIS gate, Sprint 0 hard limits, write, verify, audit.

        Args:
            register: Modbus register address (37001 or 37003)
            power_kw: Power value in kW
            label: Human-readable label for logging
            reason: Why this command was issued
            who: Who initiated (sentinel / operator / test)

        Returns:
            WriteResult
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        correlation_id = str(uuid.uuid4())[:12]
        requested_kw = power_kw

        # Sprint 0 hard power limit — enforced in code, not just config
        max_power = settings.sprint0_max_power_kw
        if power_kw > max_power:
            logger.warning(
                "Sprint 0 hard limit: clamped %.1f kW -> %.1f kW (max=%s)",
                power_kw,
                max_power,
                max_power,
            )
            power_kw = max_power

        clamped_kw = power_kw
        register_value = int(power_kw * REGISTER_SCALE)

        # 1. AEGIS gate check
        if not self._aegis_enabled:
            result = WriteResult(
                success=True,  # "success" in that the pipeline worked
                register=register,
                value_kw=power_kw,
                register_value=register_value,
                aegis_blocked=True,
                demo_mode=self._is_demo,
                timestamp=timestamp,
                correlation_id=correlation_id,
                requested_kw=requested_kw,
                clamped_kw=clamped_kw,
                reason=reason or label,
                who=who,
                end_timestamp=datetime.now(timezone.utc).isoformat(),
            )
            logger.info(
                "AEGIS blocked: %s %.1f kW -> register %d (gate closed) [%s]",
                label,
                power_kw,
                register,
                correlation_id,
            )
            self._audit_log(result, label)
            self._write_history.append(result)
            return result

        # 2. Demo mode — log only, no TCP
        if self._is_demo:
            result = WriteResult(
                success=True,
                register=register,
                value_kw=power_kw,
                register_value=register_value,
                verified=True,
                demo_mode=True,
                timestamp=timestamp,
                correlation_id=correlation_id,
                requested_kw=requested_kw,
                clamped_kw=clamped_kw,
                reason=reason or label,
                who=who,
                end_timestamp=datetime.now(timezone.utc).isoformat(),
            )
            logger.info(
                "DEMO write: %s %.1f kW -> register %d (value=%d) [%s]",
                label,
                power_kw,
                register,
                register_value,
                correlation_id,
            )
            self._audit_log(result, label)
            self._write_history.append(result)
            return result

        # 3. Real Modbus TCP write
        start = time.monotonic()
        try:
            connected = await self._ensure_connected()
            if not connected:
                result = WriteResult(
                    success=False,
                    register=register,
                    value_kw=power_kw,
                    register_value=register_value,
                    error="Modbus TCP connection failed",
                    timestamp=timestamp,
                    correlation_id=correlation_id,
                    requested_kw=requested_kw,
                    clamped_kw=clamped_kw,
                    reason=reason or label,
                    who=who,
                    end_timestamp=datetime.now(timezone.utc).isoformat(),
                )
                self._audit_log(result, label)
                self._write_history.append(result)
                return result

            # Write i32 as two 16-bit registers (big-endian)
            high_word = (register_value >> 16) & 0xFFFF
            low_word = register_value & 0xFFFF

            write_resp = await self._client.write_registers(
                register,
                [high_word, low_word],
                slave=settings.modbus_bess_unit_id,
            )

            latency_ms = (time.monotonic() - start) * 1000

            if write_resp.isError():
                result = WriteResult(
                    success=False,
                    register=register,
                    value_kw=power_kw,
                    register_value=register_value,
                    error=f"Modbus write error: {write_resp}",
                    timestamp=timestamp,
                    write_latency_ms=latency_ms,
                    correlation_id=correlation_id,
                    requested_kw=requested_kw,
                    clamped_kw=clamped_kw,
                    reason=reason or label,
                    who=who,
                    end_timestamp=datetime.now(timezone.utc).isoformat(),
                )
                self._audit_log(result, label)
                self._write_history.append(result)
                return result

            # 4. Read-back verification
            verified = False
            if settings.modbus_write_verify:
                verified = await self._verify_write(register, register_value)

            end_ts = datetime.now(timezone.utc).isoformat()
            result = WriteResult(
                success=True,
                register=register,
                value_kw=power_kw,
                register_value=register_value,
                verified=verified,
                timestamp=timestamp,
                write_latency_ms=latency_ms,
                correlation_id=correlation_id,
                requested_kw=requested_kw,
                clamped_kw=clamped_kw,
                reason=reason or label,
                who=who,
                end_timestamp=end_ts,
            )
            logger.info(
                "Modbus write: %s %.1f kW -> register %d (value=%d, verified=%s, %.1f ms) [%s]",
                label,
                power_kw,
                register,
                register_value,
                verified,
                latency_ms,
                correlation_id,
            )
            self._audit_log(result, label)
            self._write_history.append(result)
            return result

        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            result = WriteResult(
                success=False,
                register=register,
                value_kw=power_kw,
                register_value=register_value,
                error=str(e),
                timestamp=timestamp,
                write_latency_ms=latency_ms,
                correlation_id=correlation_id,
                requested_kw=requested_kw,
                clamped_kw=clamped_kw,
                reason=reason or label,
                who=who,
                end_timestamp=datetime.now(timezone.utc).isoformat(),
            )
            logger.error("Modbus write failed: %s [%s]", e, correlation_id)
            self._audit_log(result, label)
            self._write_history.append(result)
            return result

    async def _verify_write(self, register: int, expected_value: int) -> bool:
        """Read back register value and verify it matches the write.

        Returns True if read-back matches expected value.
        """
        try:
            read_resp = await self._client.read_holding_registers(
                register,
                count=2,
                slave=settings.modbus_bess_unit_id,
            )
            if read_resp.isError():
                logger.warning("Read-back verification failed: %s", read_resp)
                return False

            read_value = (read_resp.registers[0] << 16) | read_resp.registers[1]
            if read_value == expected_value:
                return True
            else:
                logger.warning(
                    "Read-back mismatch: wrote %d, read %d (register %d)",
                    expected_value,
                    read_value,
                    register,
                )
                return False
        except Exception as e:
            logger.warning("Read-back verification error: %s", e)
            return False

    async def check_watchdog(self) -> Optional[WriteResult]:
        """Check watchdog timer and send idle if no command received within timeout.

        Should be called periodically (e.g., every minute).
        Returns WriteResult if idle was sent, None otherwise.
        """
        if self._last_command_time == 0:
            return None

        elapsed = time.monotonic() - self._last_command_time
        if elapsed > self.WATCHDOG_TIMEOUT_S:
            logger.warning(
                "Watchdog timeout: %.0f s since last command — sending idle",
                elapsed,
            )
            result = await self.write_idle(reason="watchdog_timeout", who="watchdog")
            self._last_command_time = time.monotonic()
            return result
        return None

    def get_write_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent write history for diagnostics."""
        return [w.to_dict() for w in self._write_history[-limit:]]

    def _audit_log(self, result: WriteResult, label: str) -> None:
        """Append write result to JSONL audit log."""
        try:
            AUDIT_DIR.mkdir(parents=True, exist_ok=True)
            log_file = AUDIT_DIR / "modbus_writes.jsonl"
            entry = {
                "timestamp": result.timestamp,
                "label": label,
                **result.to_dict(),
            }
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug("Audit log write failed: %s", e)


# === Execute dispatch with write ===


async def execute_dispatch_with_write(
    site_id: str,
    action: str,
    requested_power_kw: float,
    bess_state: BESSState,
    duration_minutes: int = 15,
    reason: str = "mip_optimized",
    load_shedding_stage: int = 0,
    who: str = "sentinel",
) -> Dict[str, Any]:
    """Validate dispatch through BESSDispatchEngine, then route to ModbusBESSWriter.

    This is the unified entry point that combines constraint validation
    with hardware write (or AEGIS-blocked logging).

    Sprint 0 safety: duration_minutes is clamped to sprint0_max_duration_min.

    Returns:
        Dict with dispatch_command and write_result
    """
    # Sprint 0 hard duration limit — enforced in code
    max_dur = settings.sprint0_max_duration_min
    if duration_minutes > max_dur:
        logger.warning(
            "Sprint 0 hard limit: clamped duration %d min -> %d min",
            duration_minutes,
            max_dur,
        )
        duration_minutes = max_dur

    engine = get_bess_dispatch_engine()
    command = engine.execute_dispatch(
        site_id=site_id,
        action=action,
        requested_power_kw=requested_power_kw,
        bess_state=bess_state,
        duration_minutes=duration_minutes,
        reason=reason,
        load_shedding_stage=load_shedding_stage,
    )

    writer = get_modbus_bess_writer()
    write_result = await writer.execute_dispatch_command(command, who=who)

    return {
        "dispatch_command": command.to_dict(),
        "write_result": write_result.to_dict(),
    }


# === Singleton ===

_modbus_bess_writer: Optional[ModbusBESSWriter] = None


def get_modbus_bess_writer() -> ModbusBESSWriter:
    """Get the singleton Modbus BESS writer instance."""
    global _modbus_bess_writer
    if _modbus_bess_writer is None:
        _modbus_bess_writer = ModbusBESSWriter()
    return _modbus_bess_writer
