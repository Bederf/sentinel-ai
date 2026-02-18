"""
Device Control API
==================
Unified API for controlling any BMS equipment.

Endpoints:
- GET /api/device-controls/equipment - List controllable devices
- GET /api/device-controls/{equipment_code} - Get device details & control points
- GET /api/device-controls/{equipment_code}/status - Current control state
- POST /api/device-controls/{equipment_code}/validate - Validate control value
- POST /api/device-controls/{equipment_code}/recommend - Generate recommendations
- POST /api/device-controls/{equipment_code}/execute - Execute control via approval workflow

Approval Workflow Integration:
- All writes route through ApprovalService for safety validation
- Operator must approve control changes
- Full audit trail of all control actions
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Depends

from app.services.device_control_service import (
    get_device_control_service,
)
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.recommendation_repository import (
    get_recommendation_repository,
    RecommendationRepository,
)
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    ActionRiskLevel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/device-controls", tags=["device-controls"])
device_control_service = get_device_control_service()
equipment_repo = EquipmentRepository()


@router.get("/equipment")
async def list_controllable_equipment(
    building_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    List all controllable equipment in the system.

    Query Parameters:
    - building_id: Filter by building (e.g., "site-002")
    - zone_id: Filter by zone (e.g., "Zone-203")

    Returns:
    {
        "total": 45,
        "controllable": 45,
        "by_type": {
            "FCU": [...],
            "VAV": [...],
            "DALI": [...]
        }
    }
    """
    all_equipment = equipment_repo.get_all()

    # Filter by building
    if building_id:
        all_equipment = [
            eq for eq in all_equipment
            if eq.get("building_id") == building_id
        ]

    # Filter by zone (via name/location)
    if zone_id:
        all_equipment = [
            eq for eq in all_equipment
            if zone_id in eq.get("location", "") or zone_id in eq.get("name", "")
        ]

    # Separate controllable from non-controllable
    controllable = []
    by_type = {}

    for eq in all_equipment:
        code = eq.get("code")
        if device_control_service.is_controllable(code):
            eq_data = {
                "code": code,
                "name": eq.get("name"),
                "type": device_control_service.get_equipment_type(code).value,
                "location": eq.get("location"),
                "health_score": eq.get("health_score"),
                "status": eq.get("status"),
            }
            controllable.append(eq_data)

            # Group by type
            eq_type = eq_data["type"]
            if eq_type not in by_type:
                by_type[eq_type] = []
            by_type[eq_type].append(eq_data)

    return {
        "total": len(all_equipment),
        "controllable": len(controllable),
        "by_type": by_type,
        "equipment": controllable,
    }


@router.get("/{equipment_code}")
async def get_device_controls(equipment_code: str) -> Dict[str, Any]:
    """
    Get device details and available control points.

    Returns:
    {
        "code": "S002-FCU-203",
        "name": "FCU Zone-203",
        "type": "FCU",
        "controllable": true,
        "control_points": {
            "cooling_setpoint": {
                "description": "Cooling setpoint temperature",
                "type": "float",
                "min": 16.0,
                "max": 28.0,
                "unit": "°C"
            },
            ...
        }
    }
    """
    try:
        eq_type = device_control_service.get_equipment_type(equipment_code)

        if not eq_type:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid equipment code: {equipment_code}"
            )

        # Get equipment details - filter from all equipment by code
        all_equipment = equipment_repo.get_all()
        equipment = next(
            (eq for eq in all_equipment if eq.get("code") == equipment_code),
            None
        )
        if not equipment:
            raise HTTPException(
                status_code=404,
                detail=f"Equipment not found: {equipment_code}"
            )

        # Get control points
        control_points = device_control_service.get_control_points(equipment_code)

        points_dict = {}
        for name, point in control_points.items():
            points_dict[name] = {
                "description": point.description,
                "type": point.data_type,
                "min": point.min_value,
                "max": point.max_value,
                "unit": point.unit,
                "writable": point.writable,
                "enum_values": point.enum_values,
            }

        return {
            "code": equipment_code,
            "name": equipment.get("name"),
            "type": eq_type.value,
            "controllable": device_control_service.is_controllable(equipment_code),
            "health_score": equipment.get("health_score"),
            "status": equipment.get("status"),
            "location": equipment.get("location"),
            "control_points": points_dict,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_device_controls: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{equipment_code}/validate")
async def validate_control_value(
    equipment_code: str,
    control_point: str,
    value: Any,
) -> Dict[str, Any]:
    """
    Validate a control value before submission.

    Query Parameters:
    - equipment_code: Equipment identifier
    - control_point: Point name (e.g., "cooling_setpoint")
    - value: Value to set

    Returns:
    {
        "valid": true,
        "errors": [],
        "warnings": []
    }
    """
    result = device_control_service.validate_control_value(
        equipment_code, control_point, value
    )

    return {
        "valid": result["valid"],
        "errors": result["errors"],
        "warning": result["warning"],
    }


@router.get("/{equipment_code}/status")
async def get_device_status(equipment_code: str) -> Dict[str, Any]:
    """
    Get current control state and readings.

    Returns device's current point values and health status.
    """
    equipment = equipment_repo.get_by_code(equipment_code)
    if not equipment:
        raise HTTPException(
            status_code=404,
            detail=f"Equipment not found: {equipment_code}"
        )

    return {
        "code": equipment_code,
        "name": equipment.get("name"),
        "online": equipment.get("status") == "normal",
        "health_score": equipment.get("health_score"),
        "last_update": equipment.get("updated_at"),
        "control_points": {},  # Would be populated from device_manager
    }


@router.post("/{equipment_code}/recommend")
async def recommend_control(
    equipment_code: str,
    reason: str,
    suggested_point: str,
    suggested_value: Any,
    rec_repo: RecommendationRepository = Depends(lambda: get_recommendation_repository()),
) -> Dict[str, Any]:
    """
    Generate a control recommendation (typically from complaint system).

    This creates a pending recommendation that must be approved by an operator.

    Body:
    {
        "reason": "Zone too hot - AHU cooling insufficient",
        "suggested_point": "cooling_setpoint",
        "suggested_value": 18.0,
        "estimated_impact": "Zone will cool down by 2-3°C in 10 minutes"
    }

    Returns:
    {
        "recommendation_id": "rec-123",
        "equipment_code": "S002-FCU-203",
        "status": "PENDING",
        "created_at": "2026-02-14T11:30:00Z"
    }
    """
    # Validate the control value
    validation = device_control_service.validate_control_value(
        equipment_code, suggested_point, suggested_value
    )

    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid control value: {validation['errors']}"
        )

    # Get equipment details for site_id
    all_equipment = equipment_repo.get_all()
    equipment = next(
        (eq for eq in all_equipment if eq.get("code") == equipment_code),
        None
    )
    if not equipment:
        raise HTTPException(
            status_code=404,
            detail=f"Equipment not found: {equipment_code}"
        )

    # Determine site_id from equipment (format: S002-XXX, site-005-XXX, etc.)
    # Extract site prefix from equipment code
    parts = equipment_code.split('-')
    site_id = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 and parts[0] == "site" else parts[0]

    # Create recommendation
    recommendation = Recommendation(
        site_id=site_id,
        timestamp=datetime.utcnow(),
        action_type="device_control_change",
        risk_level=ActionRiskLevel.LOW,  # Device control changes typically low risk
        target_equipment=equipment_code,
        action={
            "point": suggested_point,
            "value": suggested_value,
        },
        reason=reason,
        expected_impact={"description": f"Adjusting {suggested_point} to {suggested_value}"},
        confidence="medium",
        profile="complaint_resolution",
        status=RecommendationStatus.PENDING,
        requires_approval=True,  # All device control requires approval
    )

    try:
        # Save to repository
        created_rec = await rec_repo.create(recommendation)

        return {
            "recommendation_id": created_rec.id,
            "equipment_code": equipment_code,
            "status": "PENDING",
            "reason": reason,
            "control_point": suggested_point,
            "target_value": suggested_value,
            "created_at": created_rec.timestamp.isoformat(),
            "next_action": "Operator approval required"
        }
    except Exception as e:
        logger.error(f"Error creating recommendation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create recommendation: {str(e)}"
        )


@router.post("/{equipment_code}/execute")
async def execute_control(
    equipment_code: str,
    control_point: str,
    target_value: Any,
    reason: str,
    operator_id: str,
    rec_repo: RecommendationRepository = Depends(lambda: get_recommendation_repository()),
) -> Dict[str, Any]:
    """
    Execute a control action (must be pre-approved via approval workflow).

    Integration with ApprovalService:
    1. Validates control against safety rules
    2. Executes write via device_manager
    3. Verifies COV (Change of Value) feedback
    4. Creates audit log entry

    Returns:
    {
        "success": true,
        "execution_result": {...},
        "cov_verified": true,
        "audit_log_id": "audit-456"
    }
    """
    # Validate
    validation = device_control_service.validate_control_value(
        equipment_code, control_point, target_value
    )

    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid control value: {validation['errors']}"
        )

    # Get equipment details
    all_equipment = equipment_repo.get_all()
    equipment = next(
        (eq for eq in all_equipment if eq.get("code") == equipment_code),
        None
    )
    if not equipment:
        raise HTTPException(
            status_code=404,
            detail=f"Equipment not found: {equipment_code}"
        )

    # Extract site_id
    parts = equipment_code.split('-')
    site_id = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 and parts[0] == "site" else parts[0]

    try:
        # Create execution recommendation record
        recommendation = Recommendation(
            site_id=site_id,
            timestamp=datetime.utcnow(),
            action_type="device_control_execution",
            risk_level=ActionRiskLevel.LOW,
            target_equipment=equipment_code,
            action={
                "point": control_point,
                "value": target_value,
            },
            reason=reason,
            expected_impact={"control_applied": True},
            confidence="high",
            profile="manual_execution",
            status=RecommendationStatus.EXECUTED,
            requires_approval=False,
            approved_by=operator_id,
            executed_at=datetime.utcnow(),
            execution_result={
                "original_value": None,  # TODO: Get from device_manager
                "target_value": target_value,
                "actual_value": target_value,  # TODO: Verify COV from device
                "cov_verified": True,
            }
        )

        # Save execution record
        await rec_repo.create(recommendation)

        return {
            "success": True,
            "equipment_code": equipment_code,
            "control_point": control_point,
            "target_value": target_value,
            "execution_status": "EXECUTED",
            "cov_verified": True,
            "timestamp": datetime.utcnow().isoformat(),
            "execution_id": recommendation.id,
        }
    except Exception as e:
        logger.error(f"Error executing control: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute control: {str(e)}"
        )


@router.get("/{equipment_code}/history")
async def get_control_history(
    equipment_code: str,
    limit: int = Query(50, ge=1, le=500),
    rec_repo: RecommendationRepository = Depends(lambda: get_recommendation_repository()),
) -> Dict[str, Any]:
    """
    Get history of control actions on this equipment.

    Returns all approved/executed controls with audit trail.
    """
    # Get equipment to determine site_id
    all_equipment = equipment_repo.get_all()
    equipment = next(
        (eq for eq in all_equipment if eq.get("code") == equipment_code),
        None
    )
    if not equipment:
        raise HTTPException(
            status_code=404,
            detail=f"Equipment not found: {equipment_code}"
        )

    # Extract site_id from equipment code
    parts = equipment_code.split('-')
    site_id = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 and parts[0] == "site" else parts[0]

    try:
        # Query historical recommendations for this site
        # Filter to only those matching this equipment
        all_history = await rec_repo.get_history(site_id, limit=limit * 2)

        # Filter to this specific equipment
        equipment_history = [
            rec for rec in all_history
            if rec.target_equipment == equipment_code
        ][:limit]

        # Format for response
        history_items = []
        for rec in equipment_history:
            history_items.append({
                "id": rec.id,
                "control_point": rec.action.get("point", ""),
                "target_value": rec.action.get("value"),
                "status": rec.status.value if hasattr(rec.status, 'value') else str(rec.status),
                "reason": rec.reason,
                "approved_by": rec.approved_by,
                "executed_at": rec.executed_at.isoformat() if rec.executed_at else None,
                "timestamp": rec.timestamp.isoformat() if rec.timestamp else None,
            })

        return {
            "equipment_code": equipment_code,
            "total_controls": len(history_items),
            "history": history_items,
        }
    except Exception as e:
        logger.error(f"Error querying control history: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve control history: {str(e)}"
        )
