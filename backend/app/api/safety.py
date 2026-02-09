"""Safety API endpoints for safety rule validation and management."""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from app.services.safety_interlocks import safety_engine
from app.services.device_abstraction import device_manager
from app.services.escalation_engine import escalation_engine
from app.models.autonomous_decision import EscalationLevel

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


@router.patch("/rules/{rule_id}/toggle")
async def toggle_safety_rule(rule_id: str, request: Dict[str, Any]):
    """Toggle a safety rule's enabled status."""
    if not safety_engine._initialized:
        await safety_engine.initialize()

    enabled = request.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=400, detail="Missing 'enabled' field")

    rule = await safety_engine.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Safety rule {rule_id} not found")

    # Update the rule
    rule.enabled = enabled
    await safety_engine.save_rules_to_file()

    return {
        "success": True,
        "rule_id": rule_id,
        "enabled": enabled,
        "message": f"Safety rule '{rule.name}' {'enabled' if enabled else 'disabled'}",
    }


# Escalation API Endpoints
@router.get("/escalation/status")
async def get_escalation_status():
    """Get current escalation status."""
    if not escalation_engine._initialized:
        await escalation_engine.initialize()

    active_escalations = await escalation_engine.get_active_escalations()
    return {
        "active_escalations": [event.to_dict() for event in active_escalations],
        "active_count": len(active_escalations),
        "total_history": len(escalation_engine.escalation_history),
    }


@router.post("/escalation/acknowledge")
async def acknowledge_escalation(request: Dict[str, Any]):
    """
    Acknowledge an escalation alert.

    Request body:
    {
        "escalation_id": "esc_...",
        "acknowledged_by": "operator_name",
        "comment": "Optional comment"
    }
    """
    escalation_id = request.get("escalation_id")
    acknowledged_by = request.get("acknowledged_by")
    comment = request.get("comment")

    if not escalation_id or not acknowledged_by:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: escalation_id, acknowledged_by"
        )

    if not escalation_engine._initialized:
        await escalation_engine.initialize()

    success = await escalation_engine.acknowledge_escalation(
        escalation_id,
        acknowledged_by,
        comment
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Escalation {escalation_id} not found or already acknowledged"
        )

    return {
        "success": True,
        "message": f"Escalation {escalation_id} acknowledged by {acknowledged_by}",
        "escalation_id": escalation_id,
        "acknowledged_at": datetime.now().isoformat(),
    }


@router.get("/escalation/history")
async def get_escalation_history(
    limit: Optional[int] = 100,
    escalation_level: Optional[int] = None,
    acknowledged: Optional[bool] = None
):
    """Get escalation history with optional filtering."""
    if not escalation_engine._initialized:
        await escalation_engine.initialize()

    # Convert escalation level if provided
    esc_level = None
    if escalation_level is not None:
        esc_level = EscalationLevel(escalation_level)

    history = await escalation_engine.get_escalation_history(
        limit=limit,
        escalation_level=esc_level,
        acknowledged=acknowledged
    )

    return {
        "history": [event.to_dict() for event in history],
        "count": len(history),
    }


@router.post("/escalation/test")
async def test_escalation(request: Dict[str, Any]):
    """
    Test escalation system by creating a test escalation.

    Request body:
    {
        "device_id": "test_device",
        "point_name": "test_point",
        "escalation_level": 2
    }
    """
    device_id = request.get("device_id", "test_device")
    point_name = request.get("point_name", "test_point")
    escalation_level = request.get("escalation_level", 2)

    if not escalation_engine._initialized:
        await escalation_engine.initialize()

    level = EscalationLevel(escalation_level)
    event = await escalation_engine.test_escalation(device_id, point_name, level)

    return {
        "success": True,
        "message": f"Test escalation created at level {level.name}",
        "escalation_event": event.to_dict(),
        "notifications_sent": {
            "email": level.value >= EscalationLevel.ALERT.value,
            "slack": level.value >= EscalationLevel.CRITICAL.value,
            "dashboard": level.value >= EscalationLevel.WARNING.value,
        }
    }


@router.get("/escalation/test-email")
async def test_email_notification():
    """Test email notification system."""
    from app.services.notification_service import notification_service

    # Create a test escalation event
    from app.models.autonomous_decision import EscalationEvent, EscalationLevel

    test_event = EscalationEvent(
        id="test_email_event",
        timestamp=datetime.now(),
        device_id="email_test_device",
        device_name="Test Device",
        point_name="temperature",
        current_value=25.0,
        boundary_min=16.0,
        boundary_max=28.0,
        approach_percentage=85.0,
        escalation_level=EscalationLevel.ALERT,
        acknowledged=False,
        acknowledged_by=None,
        acknowledged_at=None,
        auto_resolved=False,
        warnings=["This is a test email notification"],
        metadata={"test": True}
    )

    # Initialize notification service if needed
    if not notification_service._initialized:
        await notification_service.initialize()

    success = await notification_service.send_email_alert(test_event)

    return {
        "success": success,
        "message": "Test email notification sent" if success else "Failed to send test email",
        "test_event": test_event.to_dict(),
    }


@router.post("/escalation/emergency-stop")
async def emergency_stop():
    """
    Execute immediate emergency stop.

    This will:
    1. Stop autonomous mode immediately
    2. Restore all devices to safe state
    3. Send emergency notifications
    """
    from app.services.emergency_handler import emergency_handler
    from app.models.autonomous_decision import EscalationEvent, EscalationLevel

    if not emergency_handler._initialized:
        await emergency_handler.initialize()

    # Create emergency escalation event
    emergency_event = EscalationEvent(
        id=f"emergency_stop_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        timestamp=datetime.now(),
        device_id="system",
        device_name="System Emergency",
        point_name="emergency_stop",
        current_value=0,
        boundary_min=None,
        boundary_max=None,
        approach_percentage=100.0,
        escalation_level=EscalationLevel.EMERGENCY,
        acknowledged=False,
        acknowledged_by=None,
        acknowledged_at=None,
        auto_resolved=False,
        warnings=["Manual emergency stop triggered"],
        metadata={"triggered_by": "api_endpoint"}
    )

    # Handle emergency
    result = await emergency_handler.handle_emergency(emergency_event)

    return {
        "success": result["status"] == "success",
        "emergency_id": result["emergency_id"],
        "actions_taken": result["actions_taken"],
        "response_time_seconds": result.get("response_time_seconds", 0),
        "devices_affected": result["devices_affected"],
        "message": "Emergency stop executed successfully" if result["status"] == "success" else "Emergency stop failed",
    }
