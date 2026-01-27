"""Safety API endpoints for safety rule validation and management."""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
import logging

from app.services.safety_interlocks import safety_engine
from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/safety", tags=["safety"])


@router.get("/health")
async def safety_health():
    """Check safety service health."""
    return {
        "status": "healthy",
        "initialized": safety_engine._initialized,
        "rule_count": len(safety_engine.rules) if safety_engine._initialized else 0,
    }


@router.get("/rules")
async def get_safety_rules(
    device_type: Optional[str] = None,
    device_id: Optional[str] = None,
    enabled: Optional[bool] = None,
):
    """Get all safety rules with optional filtering."""
    if not safety_engine._initialized:
        await safety_engine.initialize()

    filter_dict = {}
    if device_type:
        filter_dict["device_type"] = device_type
    if device_id:
        filter_dict["device_id"] = device_id
    if enabled is not None:
        filter_dict["enabled"] = enabled

    rules = await safety_engine.list_rules(filter_dict)
    return {
        "rules": [rule.to_dict() for rule in rules],
        "count": len(rules),
    }


@router.get("/rules/{rule_id}")
async def get_safety_rule(rule_id: str):
    """Get a specific safety rule by ID."""
    if not safety_engine._initialized:
        await safety_engine.initialize()

    rule = await safety_engine.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Safety rule {rule_id} not found")

    return rule.to_dict()


@router.post("/validate")
async def validate_control_action(request: Dict[str, Any]):
    """
    Validate a control action against safety rules.

    Request body:
    {
        "device_id": "device_001",
        "point_name": "temperature_setpoint",
        "value": 25.0
    }
    """
    device_id = request.get("device_id")
    point_name = request.get("point_name")
    value = request.get("value")

    if not device_id or not point_name or value is None:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: device_id, point_name, value"
        )

    # Get device
    device = await device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    # Validate control action
    validation_result = await safety_engine.validate_control(device, point_name, value)

    return {
        "validation": validation_result,
        "device_id": device_id,
        "point_name": point_name,
        "value": value,
    }


@router.post("/rules")
async def create_safety_rule(rule_data: Dict[str, Any]):
    """Create a new safety rule."""
    if not safety_engine._initialized:
        await safety_engine.initialize()

    try:
        rule = await safety_engine.add_rule(rule_data)
        # Save to file
        await safety_engine.save_rules_to_file()
        return {
            "success": True,
            "rule": rule.to_dict(),
            "message": f"Safety rule '{rule.name}' created successfully",
        }
    except Exception as e:
        logger.error(f"Failed to create safety rule: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create safety rule: {str(e)}")


@router.put("/rules/{rule_id}")
async def update_safety_rule(rule_id: str, rule_data: Dict[str, Any]):
    """Update an existing safety rule."""
    if not safety_engine._initialized:
        await safety_engine.initialize()

    # Remove ID from update data to prevent changing it
    rule_data.pop("id", None)

    # Get existing rule
    existing_rule = await safety_engine.get_rule(rule_id)
    if not existing_rule:
        raise HTTPException(status_code=404, detail=f"Safety rule {rule_id} not found")

    # Create updated rule
    updated_data = {**existing_rule.to_dict(), **rule_data}
    updated_data["id"] = rule_id  # Ensure ID stays the same

    # Remove old rule and add updated one
    await safety_engine.remove_rule(rule_id)
    rule = await safety_engine.add_rule(updated_data)

    # Save to file
    await safety_engine.save_rules_to_file()

    return {
        "success": True,
        "rule": rule.to_dict(),
        "message": f"Safety rule '{rule.name}' updated successfully",
    }


@router.delete("/rules/{rule_id}")
async def delete_safety_rule(rule_id: str):
    """Delete a safety rule."""
    if not safety_engine._initialized:
        await safety_engine.initialize()

    success = await safety_engine.remove_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Safety rule {rule_id} not found")

    # Save to file
    await safety_engine.save_rules_to_file()

    return {
        "success": True,
        "message": f"Safety rule {rule_id} deleted successfully",
    }


@router.get("/devices/{device_id}/status")
async def get_device_safety_status(device_id: str):
    """Get safety status for a specific device."""
    if not safety_engine._initialized:
        await safety_engine.initialize()

    device = await device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    safety_status = await safety_engine.get_device_safety_status(device)
    return safety_status


@router.get("/devices/{device_id}/applicable-rules")
async def get_device_applicable_rules(device_id: str):
    """Get safety rules applicable to a specific device."""
    if not safety_engine._initialized:
        await safety_engine.initialize()

    device = await device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    applicable_rules = await safety_engine.get_rules_for_device(device)
    return {
        "device_id": device_id,
        "device_name": device.name,
        "applicable_rules": [rule.to_dict() for rule in applicable_rules],
        "count": len(applicable_rules),
    }