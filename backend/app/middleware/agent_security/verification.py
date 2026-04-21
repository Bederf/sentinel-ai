"""Post-Action Verification Service — Phase 120-02.

Decorator-based registry that reads back actual system state after critical
tool actions and compares it to the expected state.  Addresses the failure
mode where agents claim completion while system state contradicts it.

Critical for BMS safety: incorrect setpoints can damage equipment.

Usage:
    from app.middleware.agent_security.verification import verification_runner

    result = await verification_runner.verify(
        tool="work_orders",
        action="create",
        args={"work_order_id": "WO-20260225-ABC12345", "title": "Fix AHU", ...}
    )
    if not result.all_passed:
        logger.warning("Post-action verification failed: %s", result.summary)
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional service imports — module-level so tests can patch them.
# If a service is unavailable the verifier returns ERROR gracefully.
# ---------------------------------------------------------------------------

try:
    from app.database.repositories.work_order_repository import (
        WorkOrderRepository as _WorkOrderRepository,
    )
except Exception:  # pragma: no cover
    _WorkOrderRepository = None  # type: ignore[assignment,misc]

try:
    from app.services.niagara.bacnet_client import BACnetClient as _BACnetClient
except Exception:  # pragma: no cover
    _BACnetClient = None  # type: ignore[assignment,misc]

try:
    from app.database.supabase_client import (
        get_supabase_client as _get_supabase_client,
    )
except Exception:  # pragma: no cover
    _get_supabase_client = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------


class VerificationStatus(StrEnum):
    """Outcome of a single verification step."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass
class VerificationEvidence:
    """Evidence from one verification check."""

    verification_id: str
    timestamp: str
    action: str
    target: str
    expected_state: dict[str, Any]
    actual_state: dict[str, Any]
    status: VerificationStatus
    detail: str
    duration_ms: float


@dataclass
class VerificationResult:
    """Aggregated outcome of all verification steps for one action."""

    overall_status: VerificationStatus
    steps: list[VerificationEvidence] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """True when every step is PASSED or SKIPPED (no FAILED/ERROR)."""
        return all(s.status in (VerificationStatus.PASSED, VerificationStatus.SKIPPED) for s in self.steps)

    @property
    def summary(self) -> str:
        """Human-readable one-liner."""
        counts: dict[str, int] = {}
        for s in self.steps:
            counts[s.status.value] = counts.get(s.status.value, 0) + 1
        parts = [f"{v} {k.lower()}" for k, v in counts.items()]
        return f"Verification {self.overall_status.value}: {', '.join(parts) or 'no steps'}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Maps "tool:action" -> async verify function(args) -> VerificationEvidence
VerifierFunc = Callable[[dict[str, Any]], Awaitable[VerificationEvidence]]
_verification_registry: dict[str, VerifierFunc] = {}


def register_verifier(tool: str, action: str):
    """Decorator that registers an async verifier for a tool:action pair.

    Example::

        @register_verifier("work_orders", "create")
        async def _verify_wo_create(args: dict) -> VerificationEvidence:
            ...
    """

    def decorator(func: VerifierFunc) -> VerifierFunc:
        key = f"{tool}:{action}"
        _verification_registry[key] = func
        return func

    return decorator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex_token() -> str:
    """Return a short hex identifier for a verification step."""
    import secrets

    return secrets.token_hex(8)


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def _evidence(
    *,
    action: str,
    target: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    status: VerificationStatus,
    detail: str,
    duration_ms: float,
) -> VerificationEvidence:
    return VerificationEvidence(
        verification_id=_hex_token(),
        timestamp=_now_iso(),
        action=action,
        target=target,
        expected_state=expected,
        actual_state=actual,
        status=status,
        detail=detail,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# VerificationRunner
# ---------------------------------------------------------------------------


class VerificationRunner:
    """Looks up a verifier, calls it, wraps errors."""

    async def verify(
        self,
        tool: str,
        action: str,
        args: dict[str, Any],
    ) -> VerificationResult:
        """Run the registered verifier for *tool*:*action*.

        - If no verifier is registered, returns SKIPPED.
        - If the verifier raises, returns ERROR (never crashes).
        """
        key = f"{tool}:{action}"
        verifier = _verification_registry.get(key)

        if verifier is None:
            ev = _evidence(
                action=action,
                target=key,
                expected={},
                actual={},
                status=VerificationStatus.SKIPPED,
                detail=f"No verifier registered for {key}",
                duration_ms=0.0,
            )
            return VerificationResult(
                overall_status=VerificationStatus.SKIPPED,
                steps=[ev],
            )

        t0 = time.monotonic()
        try:
            evidence = await verifier(args)
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error(
                "Verifier %s raised %s: %s",
                key,
                type(exc).__name__,
                exc,
            )
            evidence = _evidence(
                action=action,
                target=key,
                expected=args,
                actual={},
                status=VerificationStatus.ERROR,
                detail=f"Verifier exception: {type(exc).__name__}: {exc}",
                duration_ms=elapsed,
            )

        # Determine overall status from all steps
        steps = [evidence]
        if evidence.status == VerificationStatus.FAILED:
            logger.warning(
                "Post-action verification FAILED for %s: %s",
                key,
                evidence.detail,
            )
            overall = VerificationStatus.FAILED
        elif evidence.status == VerificationStatus.ERROR:
            overall = VerificationStatus.ERROR
        else:
            overall = evidence.status

        return VerificationResult(overall_status=overall, steps=steps)


# ---------------------------------------------------------------------------
# Built-in verifiers (5)
# ---------------------------------------------------------------------------


@register_verifier("work_orders", "create")
async def _verify_wo_create(args: dict[str, Any]) -> VerificationEvidence:
    """Read back a newly-created work order and compare key fields."""
    t0 = time.monotonic()
    wo_id = args.get("work_order_id", "")
    expected_title = args.get("title", "")
    expected_site_id = args.get("site_id", "")
    expected_priority = args.get("priority", "")

    actual: dict[str, Any] = {}

    try:
        if _WorkOrderRepository is None:
            raise ImportError("WorkOrderRepository not available")
        repo = _WorkOrderRepository()
        wo = await repo.get_work_order(wo_id)
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return _evidence(
            action="create",
            target=f"work_order:{wo_id}",
            expected={"id": wo_id, "title": expected_title},
            actual={},
            status=VerificationStatus.ERROR,
            detail=f"Could not read back work order: {type(exc).__name__}: {exc}",
            duration_ms=elapsed,
        )

    elapsed = (time.monotonic() - t0) * 1000

    if wo is None:
        return _evidence(
            action="create",
            target=f"work_order:{wo_id}",
            expected={"id": wo_id, "title": expected_title},
            actual={"found": False},
            status=VerificationStatus.FAILED,
            detail=f"Work order {wo_id} not found after creation",
            duration_ms=elapsed,
        )

    actual = {
        "id": wo.get("id", ""),
        "title": wo.get("title", ""),
        "site_id": wo.get("site_id", ""),
        "priority": wo.get("priority", ""),
        "status": wo.get("status", ""),
    }

    mismatches: list[str] = []
    if expected_title and actual["title"] != expected_title:
        mismatches.append(f"title: expected={expected_title!r}, actual={actual['title']!r}")
    if expected_site_id and actual["site_id"] != expected_site_id:
        mismatches.append(f"site_id: expected={expected_site_id!r}, actual={actual['site_id']!r}")
    if expected_priority and actual["priority"] != expected_priority:
        mismatches.append(f"priority: expected={expected_priority!r}, actual={actual['priority']!r}")
    if actual["status"] not in ("open", "scheduled", "pending"):
        mismatches.append(f"status: expected open/scheduled/pending, actual={actual['status']!r}")

    if mismatches:
        return _evidence(
            action="create",
            target=f"work_order:{wo_id}",
            expected={
                "title": expected_title,
                "site_id": expected_site_id,
                "priority": expected_priority,
                "status": "open",
            },
            actual=actual,
            status=VerificationStatus.FAILED,
            detail=f"Field mismatches: {'; '.join(mismatches)}",
            duration_ms=elapsed,
        )

    return _evidence(
        action="create",
        target=f"work_order:{wo_id}",
        expected={"id": wo_id},
        actual=actual,
        status=VerificationStatus.PASSED,
        detail="Work order verified",
        duration_ms=elapsed,
    )


@register_verifier("work_orders", "close")
async def _verify_wo_close(args: dict[str, Any]) -> VerificationEvidence:
    """Read back a work order and verify its status is closed."""
    t0 = time.monotonic()
    wo_id = args.get("work_order_id", "")

    try:
        if _WorkOrderRepository is None:
            raise ImportError("WorkOrderRepository not available")
        repo = _WorkOrderRepository()
        wo = await repo.get_work_order(wo_id)
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return _evidence(
            action="close",
            target=f"work_order:{wo_id}",
            expected={"status": "closed"},
            actual={},
            status=VerificationStatus.ERROR,
            detail=f"Could not read back work order: {type(exc).__name__}: {exc}",
            duration_ms=elapsed,
        )

    elapsed = (time.monotonic() - t0) * 1000

    if wo is None:
        return _evidence(
            action="close",
            target=f"work_order:{wo_id}",
            expected={"status": "closed"},
            actual={"found": False},
            status=VerificationStatus.FAILED,
            detail=f"Work order {wo_id} not found",
            duration_ms=elapsed,
        )

    actual_status = wo.get("status", "unknown")
    if actual_status != "closed":
        return _evidence(
            action="close",
            target=f"work_order:{wo_id}",
            expected={"status": "closed"},
            actual={"status": actual_status},
            status=VerificationStatus.FAILED,
            detail=f"Work order still {actual_status!r}, expected closed",
            duration_ms=elapsed,
        )

    return _evidence(
        action="close",
        target=f"work_order:{wo_id}",
        expected={"status": "closed"},
        actual={"status": "closed"},
        status=VerificationStatus.PASSED,
        detail="Work order confirmed closed",
        duration_ms=elapsed,
    )


@register_verifier("equipment_control", "setpoint")
async def _verify_setpoint(args: dict[str, Any]) -> VerificationEvidence:
    """Read back a control point and compare to the target setpoint.

    Allows a tolerance of +/-0.5 for temperature setpoints.
    """
    t0 = time.monotonic()
    equipment_code = args.get("equipment_code", "")
    control_point = args.get("control_point", "")
    target_value = args.get("target_value")
    tolerance = float(args.get("tolerance", 0.5))

    actual_value: float | None = None

    try:
        if _BACnetClient is None:
            raise ImportError("BACnetClient not available")
        client = _BACnetClient()
        result = await client.read_point(
            equipment_code=equipment_code,
            point_name=control_point,
        )
        if result is not None:
            actual_value = float(result.get("value", result) if isinstance(result, dict) else result)
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return _evidence(
            action="setpoint",
            target=f"{equipment_code}:{control_point}",
            expected={"value": target_value, "tolerance": tolerance},
            actual={},
            status=VerificationStatus.ERROR,
            detail=f"Could not read point: {type(exc).__name__}: {exc}",
            duration_ms=elapsed,
        )

    elapsed = (time.monotonic() - t0) * 1000

    if actual_value is None:
        return _evidence(
            action="setpoint",
            target=f"{equipment_code}:{control_point}",
            expected={"value": target_value},
            actual={"value": None},
            status=VerificationStatus.FAILED,
            detail="Could not read back control point value",
            duration_ms=elapsed,
        )

    try:
        target_float = float(target_value)
    except (TypeError, ValueError):
        # Non-numeric setpoint: exact match
        if str(actual_value) != str(target_value):
            return _evidence(
                action="setpoint",
                target=f"{equipment_code}:{control_point}",
                expected={"value": target_value},
                actual={"value": actual_value},
                status=VerificationStatus.FAILED,
                detail=f"Enum mismatch: expected={target_value!r}, actual={actual_value!r}",
                duration_ms=elapsed,
            )
        return _evidence(
            action="setpoint",
            target=f"{equipment_code}:{control_point}",
            expected={"value": target_value},
            actual={"value": actual_value},
            status=VerificationStatus.PASSED,
            detail="Setpoint matches (enum)",
            duration_ms=elapsed,
        )

    drift = abs(actual_value - target_float)
    if drift > tolerance:
        return _evidence(
            action="setpoint",
            target=f"{equipment_code}:{control_point}",
            expected={"value": target_float, "tolerance": tolerance},
            actual={"value": actual_value, "drift": drift},
            status=VerificationStatus.FAILED,
            detail=f"Setpoint drift {drift:.2f} exceeds tolerance {tolerance}",
            duration_ms=elapsed,
        )

    return _evidence(
        action="setpoint",
        target=f"{equipment_code}:{control_point}",
        expected={"value": target_float, "tolerance": tolerance},
        actual={"value": actual_value, "drift": drift},
        status=VerificationStatus.PASSED,
        detail=f"Setpoint within tolerance (drift={drift:.2f})",
        duration_ms=elapsed,
    )


@register_verifier("email_smtp", "send")
async def _verify_email_send(args: dict[str, Any]) -> VerificationEvidence:
    """Verify an email was sent by checking the canonical notification delivery log."""
    t0 = time.monotonic()
    message_id = args.get("message_id", "")

    try:
        client = _get_supabase_client() if _get_supabase_client else None
        if not client:
            raise RuntimeError("Supabase client unavailable")

        result = (
            client.table("notification_delivery_log")
            .select("id,external_message_id")
            .or_(f"id.eq.{message_id},external_message_id.eq.{message_id}")
            .limit(1)
            .execute()
        )
        found = bool(result.data)

    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return _evidence(
            action="send",
            target=f"email:{message_id}",
            expected={"message_id": message_id},
            actual={},
            status=VerificationStatus.ERROR,
            detail=f"Error reading notification delivery log: {type(exc).__name__}: {exc}",
            duration_ms=elapsed,
        )

    elapsed = (time.monotonic() - t0) * 1000

    if not found:
        return _evidence(
            action="send",
            target=f"email:{message_id}",
            expected={"message_id": message_id, "found_in_log": True},
            actual={"found_in_log": False},
            status=VerificationStatus.FAILED,
            detail=f"Message {message_id!r} not found in notification delivery log",
            duration_ms=elapsed,
        )

    return _evidence(
        action="send",
        target=f"email:{message_id}",
        expected={"message_id": message_id, "found_in_log": True},
        actual={"found_in_log": True},
        status=VerificationStatus.PASSED,
        detail="Message found in notification delivery log",
        duration_ms=elapsed,
    )


@register_verifier("database_write", "insert")
async def _verify_db_insert(args: dict[str, Any]) -> VerificationEvidence:
    """Verify a database row was inserted via Supabase or JSON fallback."""
    t0 = time.monotonic()
    table_name = args.get("table", "")
    expected_row = args.get("expected_row", {})
    row_id = expected_row.get("id", args.get("row_id", ""))

    # Try Supabase first, then JSON fallback
    actual_row: dict[str, Any] | None = None

    try:
        client = _get_supabase_client() if _get_supabase_client else None
        if client and table_name and row_id:
            result = client.table(table_name).select("*").eq("id", row_id).execute()
            if result.data and len(result.data) > 0:
                actual_row = result.data[0]
    except Exception as exc:
        logger.debug("Supabase read-back failed for %s: %s", table_name, exc)
        # Fall through to JSON fallback

    # JSON fallback: check backend/app/data/{table}.json
    if actual_row is None:
        try:
            json_path = Path(__file__).parent.parent.parent / "data" / f"{table_name}.json"
            if json_path.exists():
                with open(json_path) as f:
                    data = json.load(f)

                rows = data if isinstance(data, list) else []
                for row in rows:
                    if isinstance(row, dict) and row.get("id") == row_id:
                        actual_row = row
                        break
        except Exception as exc:
            logger.debug("JSON fallback failed for %s: %s", table_name, exc)

    elapsed = (time.monotonic() - t0) * 1000

    if actual_row is None:
        return _evidence(
            action="insert",
            target=f"{table_name}:{row_id}",
            expected=expected_row,
            actual={"found": False},
            status=VerificationStatus.FAILED,
            detail=f"Row {row_id!r} not found in {table_name}",
            duration_ms=elapsed,
        )

    # Compare expected fields against actual
    mismatches: list[str] = []
    for key, expected_val in expected_row.items():
        actual_val = actual_row.get(key)
        if actual_val != expected_val:
            mismatches.append(f"{key}: expected={expected_val!r}, actual={actual_val!r}")

    if mismatches:
        return _evidence(
            action="insert",
            target=f"{table_name}:{row_id}",
            expected=expected_row,
            actual=actual_row,
            status=VerificationStatus.FAILED,
            detail=f"Field mismatches: {'; '.join(mismatches)}",
            duration_ms=elapsed,
        )

    return _evidence(
        action="insert",
        target=f"{table_name}:{row_id}",
        expected=expected_row,
        actual=actual_row,
        status=VerificationStatus.PASSED,
        detail="Row verified in database",
        duration_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

verification_runner = VerificationRunner()
