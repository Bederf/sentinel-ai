"""Autonomous System API endpoints for autonomous decision management."""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
import logging

from app.models.auth import AuthContext
from app.security.pipeline import require_role
from app.services.autonomous_decision_engine import autonomous_decision_engine
from app.services.safety_boundary_service import safety_boundary_service
from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomous", tags=["autonomous"])


@router.get("/status")
async def get_autonomous_status():
    """Get current autonomous system status."""
    if not autonomous_decision_engine._initialized:
        await autonomous_decision_engine.initialize()

    status = await autonomous_decision_engine.get_system_status()
    return status.to_dict()


@router.post("/enable")
async def enable_autonomous_mode(auth: AuthContext = Depends(require_role(2))):
    """Enable autonomous mode."""
    if not autonomous_decision_engine._initialized:
        await autonomous_decision_engine.initialize()

    result = autonomous_decision_engine.enable_autonomous_mode()

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/disable")
async def disable_autonomous_mode(auth: AuthContext = Depends(require_role(2))):
    """Disable autonomous mode."""
    if not autonomous_decision_engine._initialized:
        await autonomous_decision_engine.initialize()

    result = autonomous_decision_engine.disable_autonomous_mode()

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.get("/decisions")
async def get_autonomous_decisions(
    limit: Optional[int] = 100, offset: Optional[int] = 0, device_id: Optional[str] = None, status: Optional[str] = None
):
    """Get autonomous decision history."""
    if not autonomous_decision_engine._initialized:
        await autonomous_decision_engine.initialize()

    # Import DecisionStatus enum
    from app.models.autonomous_decision import DecisionStatus

    # Convert status string to enum if provided
    status_enum = None
    if status:
        try:
            status_enum = DecisionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    decisions = autonomous_decision_engine.get_decision_history(
        limit=limit, offset=offset, device_id=device_id, status=status_enum
    )

    return {
        "data": [d.to_dict() for d in decisions],
        "count": len(decisions),
        "total": len(autonomous_decision_engine.decision_history),
    }


@router.get("/decisions/{decision_id}")
async def get_autonomous_decision(decision_id: str):
    """Get a specific autonomous decision."""
    if not autonomous_decision_engine._initialized:
        await autonomous_decision_engine.initialize()

    # Search for decision in history
    decision = next((d for d in autonomous_decision_engine.decision_history if d.id == decision_id), None)

    if not decision:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

    return decision.to_dict()


@router.post("/decisions/{decision_id}/approve")
async def approve_autonomous_decision(decision_id: str, auth: AuthContext = Depends(require_role(2))):
    """Approve a pending autonomous decision."""
    if not autonomous_decision_engine._initialized:
        await autonomous_decision_engine.initialize()

    # Search for decision
    decision = next((d for d in autonomous_decision_engine.decision_history if d.id == decision_id), None)

    if not decision:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

    if decision.status.value != "pending":
        raise HTTPException(
            status_code=400, detail=f"Decision {decision_id} has status {decision.status.value}, not pending"
        )

    # Execute the approved decision
    try:
        result = await autonomous_decision_engine.evaluate_and_execute(
            rule=decision.rule_triggered or "manual_approval",
            device_id=decision.device_id,
            point_name=decision.point_name,
            target_value=decision.target_value,
            decision_rationale=f"Manual approval: {decision.decision_rationale}",
        )

        return {
            "success": True,
            "message": f"Decision {decision_id} approved and executed",
            "execution_result": result.to_dict(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute decision: {str(e)}")


@router.get("/boundaries")
async def get_boundary_status(device_id: Optional[str] = None):
    """Get current boundary status for all or a specific device."""
    if not safety_boundary_service:
        logger.warning("SafetyBoundaryService not properly initialized")
        return {"data": {}, "message": "Boundary monitoring temporarily unavailable"}

    devices = await device_manager.list_devices()

    # Filter device if device_id provided
    if device_id:
        devices = [d for d in devices if d.id == device_id]
        if not devices:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    device_statuses = {}

    for device in devices:
        try:
            summary = await safety_boundary_service.get_boundary_status_summary(device)
            device_statuses[device.id] = summary
        except Exception as e:
            logger.error(f"Error getting boundary status for device {device.id}: {e}")
            device_statuses[device.id] = {
                "device_id": device.id,
                "device_name": device.name,
                "error": str(e),
                "overall_status": "error",
            }

    return {"data": device_statuses, "count": len(device_statuses)}


@router.post("/boundaries/update")
async def update_boundary_config(request: Dict[str, Any], auth: AuthContext = Depends(require_role(2))):
    """Update boundary configuration for a device/point."""
    device_id = request.get("device_id")
    point_name = request.get("point_name")
    new_boundaries = request.get("new_boundaries", {})

    if not device_id or not point_name:
        raise HTTPException(status_code=400, detail="Missing required fields: device_id, point_name")

    device = await device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    try:
        success = await safety_boundary_service.update_boundary_config(
            device_id=device_id, point_name=point_name, new_boundaries=new_boundaries
        )

        if success:
            return {"success": True, "message": f"Boundary configuration updated for {device_id}.{point_name}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update boundary configuration")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating boundary: {str(e)}")


@router.get("/performance")
async def get_autonomous_performance(days: Optional[int] = 7):
    """Get autonomous system performance metrics."""
    if not autonomous_decision_engine._initialized:
        await autonomous_decision_engine.initialize()

    from datetime import datetime, timedelta

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Filter decisions for the date range
    period_decisions = [d for d in autonomous_decision_engine.decision_history if start_date <= d.timestamp <= end_date]

    total = len(period_decisions)
    successful = len([d for d in period_decisions if d.status.value == "success"])
    blocked = len([d for d in period_decisions if d.status.value == "blocked"])
    failed = len([d for d in period_decisions if d.status.value == "failed"])
    cancelled = len([d for d in period_decisions if d.status.value == "cancelled"])

    success_rate = (successful / total * 100) if total > 0 else 0

    # Calculate average execution time
    execution_times = [d.execution_time_ms for d in period_decisions if d.execution_time_ms is not None]
    avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0

    return {
        "period_days": days,
        "total_decisions": total,
        "successful": successful,
        "blocked": blocked,
        "failed": failed,
        "cancelled": cancelled,
        "success_rate": round(success_rate, 2),
        "avg_execution_time_ms": round(avg_execution_time, 2),
        "safety_score": await calculate_safety_score(period_decisions),
    }


async def calculate_safety_score(decisions):
    """Calculate safety score based on decision outcomes."""
    from app.models.autonomous_decision import DecisionStatus

    if not decisions:
        return 100.0

    # Count blocked/failed decisions (indicates safety system working)
    blocked_or_failed = len([d for d in decisions if d.status in (DecisionStatus.BLOCKED, DecisionStatus.FAILED)])

    # More blocked/failed decisions = higher safety score (system is protective)
    # But too many might indicate system is too restrictive
    safety_burden = min(blocked_or_failed / len(decisions), 0.3)  # Cap at 30%

    # Base score starts at 100
    # Bonus for blocked/failed decisions (safety working)
    # Slight penalty for high safety burden (too restrictive)
    score = 100.0 + (blocked_or_failed * 2.0) - (safety_burden * 50.0)

    return max(0.0, min(100.0, score))


@router.post("/test")
async def test_autonomous_decision(auth: AuthContext = Depends(require_role(2))):
    """Create a test autonomous decision for local validation."""
    if not autonomous_decision_engine._initialized:
        await autonomous_decision_engine.initialize()

    # Get first available device
    devices = await device_manager.list_devices()
    if not devices:
        raise HTTPException(status_code=500, detail="No devices available for testing")

    device = devices[0]

    # Find a controllable point
    controllable_point = None
    for point_name, point in device.points.items():
        if hasattr(point, "writable") and point.writable:
            controllable_point = point_name
            break

    if not controllable_point:
        raise HTTPException(status_code=500, detail="No controllable points found on device")

    # Create a safe test decision

    try:
        decision = await autonomous_decision_engine.evaluate_and_execute(
            rule_id="test_rule",
            device_id=device.id,
            point_name=controllable_point,
            target_value=22.0,  # Safe default value
            decision_rationale="Test autonomous decision execution",
        )

        return {"success": True, "message": "Test decision executed successfully", "decision": decision.to_dict()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test decision failed: {str(e)}")
